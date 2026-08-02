# Agent Trace 可视化调试

> 配套 `docs/agent-improvements.md` §2.2 可观测性

## 目标

让 admin 能在浏览器**回放任何一次 agent 决策过程**——RAG 召回的工具、工具输入参数、工具返回、step 耗时、最终回复。

```
当前：用户在 chat 点 👎，admin 只看到 "agent 给的回复"
目标：点开 message 详情 → 时间轴：
  [1] tool_start  retrieve_knowledge
      args: { city: "北京", days: 2 }
  [2] tool_end    retrieve_knowledge  1.2s
      output: 5 POIs (宽窄巷子, 锦里, ...)
  [3] complete    total: 4.5s, 1 tool call
```

**价值**：
- **debug**：出问题时知道是 RAG 没召回、还是 LLM 编、还是 tool 报错
- **调优**：哪个 tool 慢、哪条 query 没召回 → 优化目标明确
- **面试**：可视化 Agent 透明度是亮点

## 数据流

```
tripService.chat() 预创建空 assistant message → 拿到 messageId
  ↓
agentEngine.chat({ messageId, ... })
  ↓ processStream
traceRecorder.add() 到内存（tool_start/tool_end/complete/error）
  ↓
agent complete / error → traceRecorder.flush() → prisma.agentStep.createMany()
  ↓
GET /api/admin/agent-trace/:messageId
  ↓
traceService.getTraceByMessage() 查 prisma.agentStep
  ↓
返回 [{step: 1, type: 'tool_start', name: '...', args: {...}}, ...]
  ↓
AdminTrace.vue 时间轴渲染（van-steps + van-collapse）
```

## 使用方式

### 1. Admin Trace 页面

1. 登录 admin → /admin/trace
2. 输入 messageId 或 conversationId
3. 选中 message → 时间轴详情
4. args/output 点开折叠面板看 JSON

### 2. 从 Dashboard 跳转

在 admin dashboard "高 token + 低满意度案例" 行点 "🔍 Trace" → 直接跳到该 message 的 trace 页。

### 3. API

```bash
# 单 message 完整 trace
GET /api/admin/agent-trace/:messageId
# 响应：{ code: 200, data: { message: {...}, steps: [...] } }

# 会话最近 20 条 message 摘要
GET /api/admin/agent-trace?conversationId=N&limit=20
# 响应：{ code: 200, data: { summaries: [...] } }
```

Admin only (roleId=1)，否则 403。

## AgentStep 数据模型

```prisma
model AgentStep {
  id          Int      @id @default(autoincrement())
  messageId   Int
  step        Int          // 1, 2, 3...
  type        String       // tool_start | tool_end | chunk | complete | error
  name        String?      // tool 名
  args        Json?        // 工具入参
  output      String?      // 工具返回（截断 10KB）
  durationMs  Int?         // 工具耗时
  error       String?      // 错误信息
  createdAt   DateTime     @default(now())
  
  message     Message      @relation(fields: [messageId], references: [id], onDelete: Cascade)
  
  @@index([messageId, step])
  @@map("agent_steps")
}
```

**关键设计**：
- chunk 只累计数量不写 step（防表爆炸）
- output 截断 10KB
- onDelete Cascade（与技术数据相反于 feedback——step 是技术性数据，message 删了 step 跟着删）
- `@@index([messageId, step])` 一次查询出全部 step
- stepCounter 跨 fallback 不重置（primary LLM 失败切 fallback 时 step 连续编号）

## 性能影响

- 1 次 chat 平均 5-10 step → 1 次 createMany
- flush 失败只 warn，不影响 agent 业务
- 100 消息/秒 × 10 step = 1000 行/秒 DB 写入（MySQL 轻松）

## 关键设计决策

1. **buffer + flush**：避免 N+1 DB 写入
2. **中等粒度**：只记 tool_start/tool_end + complete + error，不记 LLM 中间
3. **chunk 不写 step**：防表爆炸（已有 SSE 流 + message.content 完整文本）
4. **onDelete Cascade**：与技术数据一致（message 删了 step 跟着删）
5. **trace 失败只 warn**：不影响 agent 业务
6. **不存 LLM 输入/输出**：隐私 + 表大小
7. **预创建 message**：tripService 在 agentEngine 之前先 create 空 message 行，拿到 messageId 注入 TraceRecorder，FK 才有效
8. **stepCounter 跨 fallback 连续**：primary LLM 失败切 fallback 时 step 编号继续累计，不重置
9. **output 截断 10KB**：由调用方（agentEngine）负责截断

## 限制

- **不存 LLM 输入/输出**（隐私 + 表大小）
- **chunk 不写 step**（防表爆炸）
- **不存中间 thought**（同 LLM 输出理由）
- **表归档**（v2）：30 天前 trace 自动清理

## 验证

```bash
# 单元测试
pnpm test
# 129 (前) + 6 (traceRecorder) = 135

# E2E
pnpm dev  # 启服务
# 跑 chat → 查 trace → 看时间轴
```

## 相关 commit

- `96d2762` feat(db): add AgentStep table
- `e6ab94e` feat(agent): add TraceRecorder
- `f2bfb6b` feat(trace): agentEngine 集成
- `de2f2e2` feat(trace): traceService query methods
- `a1ab451` feat(trace): admin API endpoints
- `96d545e` feat(trace): AdminTrace.vue + 路由
- `fe5f5fd` feat(trace): dashboard '🔍 Trace' 按钮
- `fc104d0` fix(trace): pre-create assistant message for real messageId

