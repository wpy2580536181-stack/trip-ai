# 在线反馈系统

> 实现位置：
> - 后端：`trip-server/src/services/feedbackService.ts` + `routes/feedback.routes.ts` + `controllers/feedback.controller.ts`
> - 前端：`trip-front/src/api/feedback.ts` + `components/ChatBubble.vue`
> - 数据库：`prisma/schema.prisma` 的 `Feedback` 模型

## 目标

把"agent 改完不知道好坏"从**离线评估**（eval 跑 fixture）扩展到**在线反馈**（真实用户点 👍/👎）：

- 离线 eval：受控场景、可重复、覆盖核心 case → CI 用
- 在线反馈：真实用户、不可控场景、覆盖长尾 case → 产品上线后用

## 数据流

```
用户在 ChatBubble 点 👍/👎
   ↓
POST /api/feedback  { messageId, conversationId, rating }
   ↓
feedbackService.submit
   ├─ 验证 message 属于该 user（防 IDOR）
   ├─ 防滥用：comment 截 500，tags 限 5
   └─ prisma.feedback.upsert (where: userId_messageId 复合唯一键)
       └─ 首次 create，重复 update
   ↓
DB: feedback row
```

## API

### POST /api/feedback
提交反馈（任何登录用户）

请求：
```json
{
  "messageId": 847,
  "conversationId": 206,
  "rating": 1,                    // 1 = 👍, -1 = 👎
  "comment": "推荐准",            // 可选，≤500 字符
  "tags": ["推荐准"]              // 可选，≤5 个
}
```

响应：
```json
{ "code": 200, "data": { "id": 1, "rating": 1 } }
```

### GET /api/feedback/message/:id
查某消息的统计（任何登录用户）

响应：
```json
{
  "code": 200,
  "data": { "up": 7, "down": 3, "total": 10, "satisfactionRate": 0.7 }
}
```

### GET /api/feedback/stats?days=7
全局统计（**仅 admin**）

响应：
```json
{
  "code": 200,
  "data": {
    "totalCount": 50,
    "upCount": 35,
    "downCount": 15,
    "satisfactionRate": 0.7,
    "recentDownComments": [
      { "comment": "推荐不对", "tags": ["推荐不准"], "createdAt": "2026-06-22T03:20:19.933Z" }
    ]
  }
}
```

### GET /api/feedback/list/:msgId
某消息所有反馈列表（**仅 admin**）

## 数据库设计

```prisma
model Feedback {
  id             Int      @id @default(autoincrement())
  userId         Int      @map("user_id")
  messageId      Int      @map("message_id")
  conversationId Int      @map("conversation_id")
  rating         Int                          // 1 = 👍, -1 = 👎
  comment        String?  @db.VarChar(500)
  tags           Json?
  createdAt      DateTime @default(now())
  updatedAt      DateTime @updatedAt

  user    User    @relation(fields: [userId], references: [id])
  message Message @relation(fields: [messageId], references: [id], onDelete: Cascade)

  @@unique([userId, messageId])               // 防重复
  @@index([messageId])
  @@index([rating, createdAt])               // admin 统计
  @@index([userId, createdAt])
  @@map("feedbacks")
}
```

**关键决策**：
- 唯一键 `(userId, messageId)`：同一用户对同一消息只能评一次（重复提交走 update 改评分）
- `onDelete: Cascade` on message：删消息时连带删反馈（避免孤儿）
- `user` relation 无 onDelete：删用户时**不**级联删反馈（保留历史质量数据）

## 安全性

- ✅ authMiddleware：必须登录
- ✅ IDOR 防护：controller 验证 message.conversation.userId === req.user.userId
- ✅ roleMiddleware：admin 接口权限
- ✅ rate limit：30 次/小时/IP（防刷）
- ✅ input sanitization：comment 截 500、tags 限 5 个
- ✅ pino 日志：feedbackLog 记录每次提交（含 userId/messageId/rating）

## 前端 UX

### ChatBubble 集成

- 仅 AI 消息显示（user 消息不显示）
- 仅已持久化的历史消息显示（流式中不显示）
- 按钮状态：未评 / 已赞 / 已踩 三态
- 选完按钮变蓝 + 显示"已收到反馈"
- 负反馈 1s 后 toast 提示"联系 admin 详细反馈"

```vue
<button class="feedback-btn" :class="{ active: currentRating === 1 }" @click="onFeedback(1)">
  <span>👍</span> <span v-if="currentRating === 1">有用</span>
</button>
```

### 关键代码

```typescript
const onFeedback = async (rating: FeedbackRating) => {
  if (!props.message.id || !props.conversationId) {
    showToast('消息未保存，无法反馈')
    return
  }
  await submitFeedback({
    messageId: props.message.id,
    conversationId: props.conversationId,
    rating,
  })
}
```

## 评估体系集成

在线反馈是 eval 体系最后一公里：

```
fixture 测试    离线     单元测试  →  PR 必跑
mock eval      离线     10 fixture →  PR 必跑
真实 eval      离线     10 fixture + 真实 LLM →  nightly
在线反馈       在线     真实用户    →  持续
```

**信号对比**：

| 来源 | 何时 | 数量 | 信号价值 |
|---|---|---|---|
| Fixture | 每次 PR | 10 | 受控场景、核心路径 |
| 在线反馈 | 持续 | 不限 | 真实用户、长尾 |

**如何用**：
- 改 system prompt → 跑 mock + 真实 eval 看 pass rate
- 上线后 → 持续看 admin stats 接口的 satisfactionRate
- satisfactionRate 下降 → 查 recentDownComments 看用户原话 → 加 fixture 覆盖

## 测试

`src/services/__tests__/feedbackService.test.ts` — 11 个单元测试：

- `submit` 调 upsert 传正确参数
- 重复提交走 update（userId_messageId 复合键）
- comment 截 500 / tags 限 5
- 空 tags 走 Prisma.JsonNull
- upsert 抛错不吞
- `getMessageStats` 聚合 up/down/total/satisfactionRate
- 无反馈时 satisfactionRate 为 null
- `getGlobalStats` 汇总 + 7/30 天窗口
- 无反馈时 satisfactionRate 为 0

## 实施时间

2026-06-22，单人半日。

## 后续可做

1. **前端批量管理 UI**：admin 页面展示 stats + recentDownComments
2. **自动告警**：连续 1 小时 satisfactionRate < 0.5 触发飞书/Slack 告警
3. **反馈进入 fixture**：把 "推荐不准" 之类的负反馈转成 fixture
4. **A/B 测试**：同 fixture 在新旧 agent 上的反馈差异
5. **点赞数据反哺 RAG**：点赞多的 POI 提升召回权重
