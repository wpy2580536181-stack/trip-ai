# Feedback → Fixture 自动化 设计

> 配套 `docs/feedback-dashboard.md`（admin dashboard 页面 + LLM token 统计）
> 关联 commit：`a688cbd`（token 跟踪）+ `6586425`（dashboard）

## 目标

把"在线负反馈"自动转成"回归测试 fixture 骨架"——形成质量改进闭环：

```
用户在 ChatBubble 点 👎 + 写评论"推荐不准"
  ↓
feedback 落 DB
  ↓
admin 在 dashboard 看到该 case（带 messageId、token、cache 命中率）
  ↓
admin 调 "导出为 fixture" → eval/fixtures/generated/113-foo.yaml（YAML 骨架）
  ↓
admin 手动补 expected 段（10 行 YAML）
  ↓
git commit + CI 自动跑
  ↓
未来若 agent 退化（"推荐不准"再次出现）→ CI 红 → 必须修
```

**核心价值**：把生产环境"用户真踩过的坑"自动变成 CI 测试。

---

## 范围

### In Scope

1. **CLI 脚本** `trip-server/scripts/feedback-to-fixture.ts`：
   - 输入：`--feedback-id=N`（单条）或 `--days=7`（批量导出该窗口内所有 down 反馈）
   - 输出：`eval/fixtures/generated/113-foo.yaml`（YAML 骨架，admin 补 expected）
   - 仅 admin 可用（登录态校验）

2. **API 端点** `POST /api/feedback/admin/convert-to-fixture`：
   - 输入：`{ feedbackIds: number[] }`
   - 输出：`{ files: string[] }`（生成的文件路径列表）
   - 与 CLI 共用 service 方法

3. **Service 方法** `feedbackService.convertToFixture(feedbackId: number): string`：
   - 拉 feedback + 关联 message + conversation + 整个 history
   - 拼 YAML 字符串（用 `js-yaml` 或手写序列化）
   - 返回 YAML 字符串

4. **Admin Dashboard 集成**：
   - "高 token + 低满意度案例"列表，每行加 "📋 转 fixture" 按钮
   - 弹出 modal：显示 YAML 预览 + "下载" / "复制" 按钮
   - 多选 + 批量转换按钮

5. **YAML 骨架格式**（核心）：
   ```yaml
   id: feedback-113-shanghai-restaurant
   description: 来自生产反馈 #113：用户说"推荐不准"
   tags: [feedback-imported, user-reported, restaurant]
   source:
     feedback_id: 113
     message_id: 847
     user: "eval-test"
     created_at: 2026-06-24T10:00:00Z
     original_comment: "推荐不准"
   
   input:
     message: "上海 2 天推荐几个好吃的餐厅"  # ← 从 message 取
     preferences:  # ← 从 conversation.user.preferences 取
       travelStyle: relaxed
       interests: [美食]
     history:  # ← 从 conversation.messages 重建（取该 message 之前的所有 user/assistant 轮次）
       - { role: user, content: "..." }
       - { role: assistant, content: "..." }
   
   # expected: 由 admin 手动补（下方）
   expected:
     # TODO: 填期望关键词、POI、工具调用
     must_contain_keywords: []
     must_not_contain_keywords: []
   
   evaluators:
     - schema_check
     - keyword_coverage
   ```

6. **文档** `docs/feedback-to-fixture.md`：使用流程 + 限制

### Out of Scope

- ❌ 自动写 `expected` 段（admin 手动，质量更可靠）
- ❌ 自动 commit + PR（需人工 review）
- ❌ 真实 LLM 重放旧版 agent（成本高）
- ❌ 大量批量转换（单次最多 50 条，避免手写压力）

---

## 架构

### 1. 文件结构

```
trip-server/
├── scripts/
│   └── feedback-to-fixture.ts           # NEW CLI
├── src/
│   ├── services/
│   │   ├── feedbackService.ts           # +convertToFixture()
│   │   └── fixtureConverter.ts          # NEW YAML 序列化
│   ├── controllers/
│   │   └── feedback.controller.ts        # +convertToFixture()
│   ├── routes/
│   │   └── feedback.routes.ts           # +POST /admin/convert-to-fixture
│   └── services/__tests__/
│       └── fixtureConverter.test.ts     # NEW 单元测试
└── eval/
    └── fixtures/
        ├── trip-planning/                # 现有 10 个手写 fixture
        └── generated/                    # NEW 反馈生成的骨架
            └── .gitkeep
trip-front/
└── src/
    ├── api/feedback.ts                   # +convertToFixture() API
    └── views/
        └── AdminFeedbackDashboard.vue    # "转 fixture" 按钮 + modal
```

### 2. 数据流

```
admin 在 dashboard 看到"高 token + 低满意度"case
  ↓
点 "📋 转 fixture" 按钮
  ↓
前端调 POST /api/feedback/admin/convert-to-fixture { feedbackIds: [113, 114] }
  ↓
controller 校验 admin (roleId=1)
  ↓
feedbackService.convertToFixture(feedbackId) 逐个
  ↓
fixtureConverter.toYAML(feedback) 拼字符串
  ↓
fs.writeFileSync 写 eval/fixtures/generated/{id}.yaml
  ↓
返回文件路径列表
  ↓
前端 modal 显示：YAML 预览 + "已生成 2 个文件"
  ↓
admin 跳 IDE 编辑 + 补 expected + commit
```

### 3. Service 设计

```typescript
// feedbackService.convertToFixture(feedbackId)
async convertToFixture(feedbackId: number): Promise<string> {
  const fb = await prisma.feedback.findUnique({
    where: { id: feedbackId },
    include: {
      user: { select: { username: true, preferences: true } },
    },
  })
  if (!fb) throw new Error('feedback 不存在')

  // 关联 message + 整段 conversation（取历史）
  const [message, conversation] = await Promise.all([
    prisma.message.findUnique({ where: { id: fb.messageId } }),
    prisma.conversation.findUnique({
      where: { id: fb.conversationId },
      include: {
        messages: { orderBy: { createdAt: 'asc' } },
      },
    }),
  ])
  if (!message || !conversation) throw new Error('message/conversation 不存在')

  return fixtureConverter.toYAML(fb, message, conversation)
}
```

```typescript
// fixtureConverter.toYAML(feedback, message, conversation)
function toYAML(fb, msg, conv): string {
  const history = conv.messages
    .filter(m => m.id <= msg.id)
    .filter(m => m.id !== msg.id)  // 排除目标 message 本身
    .map(m => ({ role: m.role, content: m.content }))

  return yaml.dump({
    id: `feedback-${fb.id}-${slugify(msg.content.slice(0, 30))}`,
    description: `来自生产反馈 #${fb.id}：${fb.comment?.slice(0, 30) || '(无评论)'}`,
    tags: ['feedback-imported', 'user-reported', ...(fb.tags || [])],
    source: {
      feedback_id: fb.id,
      message_id: msg.id,
      user: fb.user.username,
      created_at: fb.createdAt.toISOString(),
      original_comment: fb.comment || null,
    },
    input: {
      message: msg.content,  // 注意：asssistant 消息，所以取 user 上一轮？——见下"歧义点 1"
      preferences: fb.user.preferences || {},
      history,
    },
    expected: {
      // 留空骨架，admin 手动填
      must_contain_keywords: [],
      must_not_contain_keywords: [],
    },
    evaluators: ['schema_check', 'keyword_coverage'],
  })
}
```

### 4. CLI 设计

```bash
# 单条
pnpm ts-node scripts/feedback-to-fixture.ts --feedback-id=113

# 批量（最近 7 天所有 down 反馈）
pnpm ts-node scripts/feedback-to-fixture.ts --days=7

# 指定输出目录
pnpm ts-node scripts/feedback-to-fixture.ts --days=7 --out=eval/fixtures/generated/

# dry-run（只打印不写文件）
pnpm ts-node scripts/feedback-to-fixture.ts --days=7 --dry-run
```

**CLI 不需要 admin 鉴权**（脚本侧只读 DB + 写文件，安全等价于本地 dev 工具）。

### 5. API 端点

`POST /api/feedback/admin/convert-to-fixture`

请求：
```json
{ "feedbackIds": [113, 114] }
```

响应：
```json
{
  "data": {
    "files": [
      "eval/fixtures/generated/feedback-113-foo.yaml",
      "eval/fixtures/generated/feedback-114-bar.yaml"
    ]
  }
}
```

**校验**：
- `feedbackIds` 长度 1-50
- 全部存在
- 全部 rating=-1（不转好评）
- `req.user.roleId === 1`（admin）

**写文件路径**：`/Users/wang/Documents/trip/trip-server/eval/fixtures/generated/{id}.yaml`

### 6. 前端集成

AdminFeedbackDashboard.vue 改动：

```vue
<!-- 在高 token 案例行加按钮 -->
<div v-for="c in highTokenCases" :key="c.feedbackId" class="case-row">
  <span>case #{{ c.feedbackId }} · {{ c.usage.total }} tokens</span>
  <van-button size="small" @click="convertOne(c.feedbackId)">
    📋 转 fixture
  </van-button>
</div>

<!-- 顶部加批量按钮 -->
<van-button @click="convertBatch">批量转最近 7 天</van-button>

<!-- 转换结果 modal -->
<van-dialog v-model:show="showResult" title="已生成 fixture 骨架">
  <pre>{{ yamlPreview }}</pre>
  <template #footer>
    <van-button @click="copyAll">复制</van-button>
    <van-button type="primary" @click="showResult = false">完成</van-button>
  </template>
</van-dialog>
```

### 7. 歧义点 + 决策

#### 歧义 1：fixture.input.message 是什么？

负反馈是对**assistant 消息**点的 👎。**assistant 消息的 content** 不是 user 输入——它是 agent 输出。

3 种可能：
- **A. 取该 message 的上一条 user 消息**（推荐）—— 还原"用户当时问了啥"
- **B. 取 feedback 关联的 message.content**（assistant 输出）—— 错误，那是 agent 答的
- **C. 用整个 conversation 的最后 user turn** —— 同 A

**决策**：**A**。在 conversation.messages 里找 `< messageId` 中最后一条 role=user 的 content 作为 `input.message`。history 包含所有 user/assistant 轮次直到该 message。

#### 歧义 2：output 写到哪？

CI 跑 fixture 是从 `eval/fixtures/trip-planning/` 目录读。新生成文件放 `eval/fixtures/generated/` 目录。

**决策**：
- `eval/fixtures/generated/` 目录放**机器生成**的（带 `source: feedback_*` 元数据）
- `eval/fixtures/trip-planning/` 目录放**人工编写**的
- runner 自动扫描两个目录
- 报告里 `byTag: { 'feedback-imported': {...} }` 可看反馈来源 fixture 通过率

**需要改 runner.ts**：扫 `fixtures/**/*.yaml` 而非仅 `fixtures/trip-planning/`

#### 歧义 3：转换失败的 fallback？

- feedback 关联的 message 被删 → 跳过 + 警告
- conversation 被删 → 跳过
- content 含敏感信息（密码、token 模式） → 警告但不阻断（admin 自己看）

**决策**：**警告但继续**。CLI 末打印警告列表；admin 自己 review 文件再 commit。

---

## 错误处理

| 场景 | 行为 |
|---|---|
| feedbackId 不存在 | CLI: `❌ feedback #N 不存在`；API: 400 |
| feedbackId 关联 message 被删 | CLI: `⚠️ 跳过 #N：message 不存在`；API: 跳过该 ID，files 列表少一条 |
| 批量超 50 条 | API: 400 `最多 50 条`；CLI: 截断前 50 |
| 文件名冲突（已存在） | 写 `feedback-113-foo.yaml` 冲突 → 写 `feedback-113-foo-1.yaml` 递增 |
| fs 写失败 | API: 500 `文件写入失败`；CLI: 抛错退出 |
| 用户 preferences 字段不存在 | fallback `{}` |
| content 超过 10KB | 截断到 10KB（fixture 文件应小） |

---

## 测试

### 1. 单元测试（fixtureConverter.test.ts）

- ✅ 基础序列化：fb + msg + conv → 标准 YAML 字符串
- ✅ history 过滤：排除 messageId 之后的、排除 message 本身
- ✅ input.message 选最后一条 user turn
- ✅ tags 合并：[feedback-imported, user-reported, ...fb.tags]
- ✅ source 元数据完整
- ✅ 截断 10KB 超长 content
- ✅ slugify 特殊字符（中英文、数字、空格）

### 2. Service 集成测试

- ✅ convertToFixture 完整跑：DB fixture → YAML 字符串
- ✅ feedback 不存在抛错
- ✅ message 不存在抛错

### 3. E2E（curl）

- ✅ admin 调 API：写文件 + 200
- ✅ roleId=2 调 API：403
- ✅ feedbackId 不存在：400
- ✅ 批量 50 条：files 列表 50 个

### 4. 文档测试

- ✅ `pnpm feedback:to-fixture --days=7 --dry-run` 跑通
- ✅ 生成的 YAML 能被 `pnpm eval --real` 加载（即使 expected 为空，schema_check 仍跑）

---

## 实施步骤

1. **CLI 骨架**：`scripts/feedback-to-fixture.ts` + 解析参数
2. **fixtureConverter.ts**：`toYAML()` + slugify + 截断
3. **feedbackService.convertToFixture** 调用 converter
4. **Service 单元测试** + **converter 单元测试** + **E2E**
5. **API 端点** `POST /admin/convert-to-fixture`（admin 守卫）
6. **前端** 按钮 + modal + 批量
7. **runner 改** + 报告加 `byTag: { feedback-imported: ... }`
8. **文档** `docs/feedback-to-fixture.md`
9. **实战**：从真实负反馈生成 1 个 fixture，补 expected，git commit

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 生成的 fixture 太多污染 git | 文档里强调"人工 review 再 commit"；批量建议一次性 5-10 个 |
| fixture YAML 格式漂移 | fixtureConverter 单元测试覆盖所有字段；现有 10 个 fixture 维持不变 |
| admin 误转好评（rating=1） | API 校验跳过；CLI 警告 |
| 敏感信息落盘 | 文档警告"commit 前 review"；不自动 commit |
| runner 双目录性能 | 10 + N 个 YAML 都 <1KB，总数 <100，毫秒级 |

---

## 验证标准

1. `pnpm test` 通过（新增 7-10 个测试）
2. `pnpm typecheck` 通过
3. 真实生成 1 个 fixture 跑 `pnpm eval --real`：报告里能识别 + 跑通
4. admin dashboard 按钮可见 + 转换成功
5. roleId=2 调 API → 403
6. 文档完整可执行

---

## 关键决策摘要

- **半自动**（B 方案）：脚本生成骨架，admin 补 expected
- **input.message 选最后 user turn**（不是 assistant）
- **输出目录**：`eval/fixtures/generated/`（与 `trip-planning/` 区分）
- **CLI 不鉴权**（admin 手动执行）；API 鉴权
- **批量上限 50**（避免 admin 压力）
- **不自动 commit**（避免 review 缺失）
- **slugify 处理特殊字符**（中英文 + 数字 + 空格 → -）
