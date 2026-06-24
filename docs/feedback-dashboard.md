# Feedback Dashboard + LLM Token 统计

> 配套 commits：`a688cbd`（token 统计 + 缓存命中率）+ `6586425`（admin dashboard 页面）
> 关联文档：`docs/online-feedback.md`（在线反馈系统基础）

## 目标

把"在线反馈"从**纯统计**升级为**质量改进闭环**：

```
┌─────────────────────────────────────────────────────────┐
│  真实用户在 ChatBubble 点 👎                              │
│         ↓                                                │
│  feedback 落 DB（rating/comment/tags）                    │
│         ↓                                                │
│  TokenUsage 同步落 message.metadata（per-request 用量）  │
│         ↓                                                │
│  Admin Dashboard 聚合                                     │
│  - 满意率趋势 / 负反馈热点 / 高 token + 低满意度案例     │
│         ↓                                                │
│  优化 prompt / 加 fixture / 改进 RAG 召回                  │
└─────────────────────────────────────────────────────────┘
```

核心价值：**用"高 token + 低满意度"案例定位"烧钱但质量差"的回复**——优化 ROI 最高。

---

## 1. LLM Token 统计

### 1.1 数据流

```
DeepSeek API 响应
  ↓
ChatOpenAI (含 modelKwargs.stream_options.include_usage=true)
  ↓
AIMessageChunk (kwargs.usage_metadata.input_tokens/output_tokens)
  ↓
agentEngine 累积到 processStream 的 usage 对象
  ↓
emit onEvent({ type: 'complete', content, usage })
  ↓
tripService.persistAssistant 存 message.metadata = { usage }
  ↓
controller 转发到 SSE complete event data.usage
  ↓
前端 Chat.vue message.usage
  ↓
Admin Dashboard 聚合展示
```

### 1.2 TokenUsage 数据结构

```typescript
export interface TokenUsage {
  prompt: number      // 输入 token（含 system + history + user）
  completion: number  // 输出 token（agent 回复 + 工具调用 thought）
  total: number       // prompt + completion
  cached: number      // DeepSeek prompt cache 命中数
}
```

### 1.3 DeepSeek Prompt Cache

DeepSeek 自动启用 **prompt cache**——重复的 system prompt + 工具定义会被缓存，无需任何配置。

**关键观察**（实测）：
```
第一次 chat:  prompt=1480  cached=0     → 命中率 0%   （prefix 不匹配）
第二次 chat:  prompt=1480  cached=1408  → 命中率 95.1%（系统提示复用）
```

**为什么命中率高**：
- 同一 model + system prompt 相同 → cache key 命中
- 多轮对话后续消息 → 历史 prefix 命中
- 工具定义（`retrieve_knowledge` 等）→ cache 复用

**为什么 cached < prompt**：
- user 输入部分是动态的（每次不同）
- 一小部分 system 提示含时间戳等动态内容

### 1.4 后端关键代码

**`src/config/llm.ts`**：开启 stream usage
```typescript
new ChatOpenAI({
  // ...
  modelKwargs: streaming ? { stream_options: { include_usage: true } } : undefined,
})
```

**`src/services/agent/agentEngine.ts`**：读 usage
```typescript
} else if (event.event === 'on_chat_model_end') {
  const msg = event.data?.output as { toJSON?: () => { kwargs?: any } }
  const kwargs = msg?.toJSON?.()?.kwargs
  const um = kwargs?.usage_metadata
  const respUsage = kwargs?.response_metadata?.usage
  if (um) {
    usage.prompt += um.input_tokens ?? 0
    usage.completion += um.output_tokens ?? 0
    usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += um.input_token_details?.cache_read ?? 0
  } else if (respUsage) {
    // ... 同样从 prompt_tokens_details.cached_tokens 或 prompt_cache_hit_tokens 取
  }
}
```

**注意**：AIMessageChunk 的 `output.kwargs` 是 private（LangChain 内部约定），必须用 `toJSON().kwargs` 访问。

**`src/services/llmGuard/tokenTracker.ts`**：拆分 prompt/completion/cached
```typescript
function recordUsage(usage: { prompt: number; completion: number; cached?: number }): void {
  // ... 累加 + 写 tokenUsageLog（含 cached 字段）
}
```

### 1.5 SSE 协议扩展

**`complete` event 新加 `usage` 字段**（前端 SSEParser 自动透传）：

```json
{
  "type": "complete",
  "data": {
    "conversationId": 261,
    "usage": { "prompt": 1480, "completion": 427, "total": 1907, "cached": 1408 }
  }
}
```

---

## 2. Admin Feedback Dashboard

### 2.1 入口

- **路由**：`/admin/feedback`（仅 admin，roleId=1）
- **菜单**：Home.vue 4 宫格"反馈 Dashboard"（admin 可见）
- **路由守卫**：`router.beforeEach` 检查 `meta.requiresAdmin` + `userInfo.roleId === 1`

### 2.2 页面结构（5 个区块）

```
┌────────────────────────────────────────┐
│  4 stat cards:                          │
│  ┌──────┬──────┬──────┬──────┐          │
│  │ 总反馈 │ 满意率 │ 👍 │ 👎 │          │
│  └──────┴──────┴──────┴──────┘          │
│  满意率颜色: ≥80% 绿 / ≥50% 橙 / 否则红 │
├────────────────────────────────────────┤
│  每日趋势图（CSS 自绘 bar chart）       │
│  [绿色 👍] + [红色 👎] 堆叠             │
│  X 轴: 日期 / Y 轴: 自动归一化          │
├────────────────────────────────────────┤
│  最近负反馈评论                          │
│  [时间] [tag] [tag]  "评论文本..."      │
├────────────────────────────────────────┤
│  高 token + 低满意度案例                │
│  聚合: N 个 / 总 X tokens / 平均 cache Y% │
│  每条: 用户/时间/total/prompt/completion/cache%│
└────────────────────────────────────────┘
```

### 2.3 API 列表（3 个，全部 admin only）

| 路径 | 方法 | 用途 |
|---|---|---|
| `/api/feedback/stats?days=7` | GET | 全局统计（4 个数字 + recent comments） |
| `/api/feedback/admin/daily-stats?days=30` | GET | 每日趋势数据（raw SQL GROUP BY DATE） |
| `/api/feedback/admin/high-token-low-satisfaction?days=7&limit=20` | GET | 高 token 案例（join message.metadata.usage） |

**权限**：3 个都要求 `req.user.roleId === 1`，否则 403。

### 2.4 `getDailyStats` 实现

```sql
SELECT
  DATE(created_at) as date,
  SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as up,
  SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) as down
FROM feedbacks
WHERE created_at >= ?  -- 起始日期（含今天）
GROUP BY DATE(created_at)
ORDER BY date ASC
```

**后处理**：补 0 缺失日期，返回 N 个 `{date, up, down, total, satisfactionRate}`。

### 2.5 `getHighTokenLowSatisfaction` 实现

1. 查 `feedback`（rating=-1，最近 7 天，最多 200 条），include user
2. 关联 `message`（取 metadata.usage + content preview）
3. 组装 Case：`{feedbackId, messageId, user, comment, tags, messagePreview, usage, createdAt}`
4. `usage.cacheHitRate = cached / prompt`（0-1 浮点）
5. 按 `usage.total` 降序排，取 top `limit`
6. **无 usage 的 case 排最后**（total=-1 兜底）

### 2.6 关键数据流（完整链路）

```
真实用户点 👎
  ↓
POST /api/feedback { messageId, rating: -1, comment, tags }
  ↓
feedback 落 DB（带 userId_messageId 唯一键）
  ↓
（同时）message.metadata = { usage: { prompt, completion, total, cached } }
  ↓
Admin 调 /admin/high-token-low-satisfaction
  ↓
feedbackService join feedback + message，组装 Case
  ↓
前端 AdminFeedbackDashboard 渲染
  ↓
Admin 看到 "case 113: prompt=3000, completion=500, cache 0%, 用户说'推荐不准'"
  ↓
优化 prompt 或加 fixture 防回归
```

---

## 3. 端到端示例

### 3.1 真实 E2E（curl 验证）

**a. eval-test 改成 admin**（本地测试用）
```bash
node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.user.update({ where: { username: 'eval-test' }, data: { roleId: 1 } })
  .then(() => p.\$disconnect());
"
```

**b. 启服务**
```bash
cd trip-server
npx ts-node src/index.ts
```

**c. 登录拿 token**
```bash
LOGIN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"eval-test","password":"EvalTest@2026"}')
TOKEN=$(echo "$LOGIN" | jq -r .data.token)
```

**d. 调 admin API**
```bash
# 全局统计
curl -s "http://localhost:3000/api/feedback/stats?days=7" \
  -H "Authorization: Bearer $TOKEN" | jq

# 日趋势
curl -s "http://localhost:3000/api/feedback/admin/daily-stats?days=7" \
  -H "Authorization: Bearer $TOKEN" | jq

# 高 token 案例
curl -s "http://localhost:3000/api/feedback/admin/high-token-low-satisfaction?days=7&limit=20" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**e. roleId=2 测试 403**
```bash
# 改回 roleId=2
# （重登录拿新 token，因为 JWT roleId 是快照）
# 调 admin API → 403 Forbidden
```

### 3.2 浏览器流程

1. 登录（admin 账号）→ Home 页 4 宫格有"反馈 Dashboard"
2. 点"反馈 Dashboard"→ `/admin/feedback`
3. 选 7/30 天 tab → 4 个数字 + 趋势图 + 评论 + 案例
4. 翻看"高 token + 低满意度案例"→ 优化 prompt / 加 fixture
5. 退出登录 → 再访问 `/admin/feedback` → 自动跳 Home（route 守卫）

---

## 4. 已知限制

### 4.1 内存数据
- `tokenUsageLog` 是**内存**（`/token` 页面 + dashboard 显示整体命中率）
- 服务重启后清零
- **改进方向**：加持久化（写 MySQL 或 Redis）

### 4.2 趋势图 SQL 兼容性
- `getDailyStats` 用 raw SQL `DATE(created_at)` + `SUM(CASE WHEN ...)`
- **MySQL 兼容**（已验证）
- PostgreSQL 需调整：`DATE(created_at)` 改为 `created_at::date`，其他基本相同

### 4.3 cached_tokens 字段差异
- DeepSeek 用 `prompt_tokens_details.cached_tokens`（新）
- 部分 API 用 `prompt_cache_hit_tokens`（旧）
- LangChain `usage_metadata` 用 `input_token_details.cache_read`（Anthropic 风格）
- 代码兼容全部 3 种格式

### 4.4 roleId 检查时机
- 后端检查 `req.user.roleId`——来自 JWT payload
- JWT 在登录时签发，roleId 是**登录时刻的快照**
- 改 DB 的 roleId 后必须**重登录**才生效
- 已通过 e2e 验证（roleId=2 → 403）

### 4.5 无 usage 的 case
- 旧消息（没存 metadata.usage）→ `usage: null`，排在 top 列表**最后**
- 新消息（Task 1 之后）→ 都有 usage，能看到 cache 命中率

---

## 5. 测试覆盖

| 文件 | 测试数 | 覆盖 |
|---|---|---|
| `feedbackService.test.ts` | **16** | submit / getMessageStats / getGlobalStats / getHighTokenLowSatisfaction (sort/null usage/missing msg) / getDailyStats (有数据/空数据) |
| `stream.test.ts` | **15** | ResumableStream 6 API + 上次 CORS/SSE id 字段 + flushHeaders |
| `streamStore.test.ts` | **17** | Redis 6 API + 损坏 event / size limit / 并发 / TTL |
| **总计** | **111** | 全部通过 |

**前端测试**（node:test，无 vitest 依赖）：
- `stream-parser.test.mjs`：19 个测试覆盖 SSE 解析 + 退避

---

## 6. 实施时间线

| 日期 | 任务 | commit |
|---|---|---|
| 2026-06-24 | Task 1: LLM token 统计 + 缓存命中率 | `0841296` |
| 2026-06-24 | Task 1.5: cached_tokens 字段 + dashboard 支持 | `a688cbd` |
| 2026-06-25 | Task 2: admin dashboard 页面 | `6586425` |
| TBD | Task 3: 反馈 → fixture 自动化（最大价值 ROI） | 待开始 |

---

## 7. 相关文件

| 文件 | 作用 |
|---|---|
| `trip-server/src/types/agent.ts` | TokenUsage interface 定义 |
| `trip-server/src/services/agent/agentEngine.ts` | on_chat_model_end 读 usage |
| `trip-server/src/services/llmGuard/tokenTracker.ts` | 拆分 prompt/completion/cached |
| `trip-server/src/services/llmGuard/tokenUsageLog.ts` | TokenUsageLogEntry 新增 cached |
| `trip-server/src/services/feedbackService.ts` | getDailyStats + getHighTokenLowSatisfaction |
| `trip-server/src/services/tripService.ts` | persistAssistant 存 usage |
| `trip-server/src/controllers/feedback.controller.ts` | getDailyStats controller |
| `trip-server/src/controllers/trip.controller.ts` | SSE complete event 带 usage |
| `trip-server/src/config/llm.ts` | stream_options.include_usage |
| `trip-front/src/views/AdminFeedbackDashboard.vue` | admin dashboard 页面 |
| `trip-front/src/views/TokenUsage.vue` | 加缓存命中率卡片 |
| `trip-front/src/views/Chat.vue` | Message.usage + onComplete 存 |
| `trip-front/src/views/Home.vue` | 加"反馈 Dashboard"菜单 |
| `trip-front/src/router/index.ts` | /admin/feedback 路由 + 守卫 |
| `docs/online-feedback.md` | 在线反馈系统基础文档（前置） |
