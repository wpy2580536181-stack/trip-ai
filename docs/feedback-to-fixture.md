# Feedback → Fixture 自动化

> 配套 `docs/feedback-dashboard.md`、`docs/online-feedback.md`
> 关联计划：`docs/superpowers/plans/2026-06-25-feedback-to-fixture.md`

## 目标

把生产环境"用户真踩过的坑"自动转成 CI 测试——质量改进闭环最后一公里。

## 流程

```
用户在 ChatBubble 点 👎 + 写评论"推荐不准"
  ↓
admin 在 dashboard 看到该 case
  ↓
点 "📋 转 fixture" 按钮（或批量）
  ↓
生成 eval/fixtures/generated/{id}-{user}.yaml 骨架
  ↓
admin 到 IDE 补 expected 段（10 行 YAML）
  ↓
git commit + CI 自动跑
  ↓
未来若 agent 退化 → CI 红 → 必须修
```

## 3 种使用方式

### 1. Admin Dashboard（推荐给非技术使用）

1. 登录 admin 账号 → Home → 反馈 Dashboard
2. "高 token + 低满意度案例"区，每行点 "📋 转 fixture"
3. 弹 modal 显示文件路径
4. 到 IDE 编辑 `trip-server/eval/fixtures/generated/*.yaml`
5. 补 `expected.must_contain_keywords` 和 `expected.must_not_contain_keywords`
6. `git add` + commit

### 2. CLI

```bash
cd trip-server

# 单条
pnpm feedback:to-fixture --feedback-id=113

# 批量（最近 7 天所有负反馈，最多 50 条）
pnpm feedback:to-fixture --days=7

# 预览不写
pnpm feedback:to-fixture --days=7 --dry-run
```

### 3. API

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"..."}' | jq -r .data.token)

curl -X POST http://localhost:3000/api/feedback/admin/convert-to-fixture \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"feedbackIds": [113, 114]}'
```

## 生成的 YAML 骨架

```yaml
id: feedback-113-eval-test-shanghai-food
description: 来自生产反馈 #113：推荐不准
tags: [feedback-imported, user-reported, recommend]
source:
  feedback_id: 113
  message_id: 847
  user: eval-test
  created_at: 2026-06-24T10:00:00.000Z
  original_comment: 推荐不准
  bad_response: |  # agent 当时给"坏"回复（admin 看到上下文）
    ...
input:
  message: 上海 2 天推荐几个好吃的  # ← 自动取的 user turn
  preferences: { travelStyle: relaxed, interests: [美食] }
  history:
    - { role: user, content: ... }
    - { role: assistant, content: ... }
expected:
  # TODO: 手动补
  must_contain_keywords: []
  must_not_contain_keywords: []
evaluators:
  - schema_check
  - keyword_coverage
```

## Admin 补 expected 模板

```yaml
expected:
  # 案例：用户说"推荐不准"
  must_contain_keywords: [推荐, 餐厅, 美食]  # 该有的关键词
  must_not_contain_keywords: [酒吧, 夜店]  # 不该有的

  # 案例：用户说"没解决宠物问题"
  must_contain_keywords: [宠物, 友好, 允许携带]

  # 案例：用户说"行程太紧凑"
  max_activities_per_day: 4

  # 工具调用：期望 RAG 召回
  tool_calls:
    - { name: retrieve_knowledge, min_calls: 1 }
```

## 报告

跑 `pnpm eval --real` 后，报告里：
- `byTag.feedback-imported`：所有反馈来源 fixture 通过率
- `byTag.user-reported`：同上
- 单个 case 显示 `source: feedback #113` 元数据（在 fixture description 里）

## 限制

- **半自动**：`expected` 段必须 admin 手动补（10 行 YAML，2-3 分钟）
- **批量上限 50**：避免 admin 压力
- **不自动 commit**：避免 review 缺失
- **历史截断 10KB**：超大 content 截断（fixture 文件应 < 100KB）
- **不转好评**（rating=1）：CLI/API 都跳过

## 验证

```bash
# 生成的 fixture 能跑
pnpm eval --real
# 看到 "feedback-113-eval-test-shanghai-food" 通过/失败

# 单元测试
pnpm test
# fixtureConverter 15 个 + feedbackService 5 个 = 20 个
```

## 关键设计决策

1. **input.message 选 < messageId 的最后 user turn**：spec 决策（`messageId` 指向被点 👎 的 assistant 消息）
2. **history 含 target 之前所有轮次**：多轮对话上下文完整保留
3. **bad_response 字段**：admin 看到 agent 当时给的"坏"回复，方便补 expected
4. **冲突解决**：文件已存在时自动追加 `-1`, `-2` 后缀
5. **不转好评**：质量改进闭环只针对 down 反馈
6. **CLI/API 共用 service**：相同逻辑 3 入口
