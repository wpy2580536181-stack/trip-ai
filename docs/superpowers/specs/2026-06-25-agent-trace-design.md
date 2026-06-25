# Agent 可视化调试工具 设计

> 配套 `docs/agent-improvements.md` §2.2 可观测性
> 关联 commit：`a688cbd`（token 跟踪）、`6586425`（admin dashboard）、`db7982d`（feedback-to-fixture）

## 目标

让 admin 能在浏览器**回放任何一次 agent 决策过程**——RAG 召回的工具、工具输入参数、工具返回、step 耗时、最终回复。

```
当前：用户在 chat 点 👎，admin 只看到 "agent 给的回复"
      不知道 agent 调了几个工具、召回了什么、为什么这么答

目标：点开 message 详情 → 时间轴：
  [1] chunk "为您推荐..."   42ms
  [2] tool_start  retrieve_knowledge  
      args: { city: "北京", days: 2 }
  [3] tool_end    retrieve_knowledge  1.2s
      output: 5 POIs (宽窄巷子, 锦里, ...)
  [4] chunk "您可以..."  38ms
  [5] complete  total: 4.5s, 3 chunks, 1 tool call
```

**价值**：
- **debug**：出问题时知道是 RAG 没召回、还是 LLM 编、还是 tool 报错
- **调优**：哪个 tool 慢、哪条 query 没召回 → 优化目标明确
- **面试**：可视化 Agent 透明度是亮点（LangChain 生态少见）

---

## 范围

### In Scope

1. **DB schema 新表** `AgentStep`（Prisma migration）
   - 字段：id, messageId, step (1-N), type (tool_start/tool_end/chunk/complete), name?, args?, output?, durationMs?, error?, createdAt
   - 索引：messageId + step（按 message 查全部 step）

2. **agentEngine 集成**：
   - `processStream` 在 on_chat_model_end / tool_start / tool_end / complete 各插入 1 条 AgentStep
   - 失败时也写 error step
   - chunk 太多（>50）不写 step，只累计 chunkCount（防表爆炸）

3. **API 端点**（admin only）：
   - `GET /api/admin/agent-trace/:messageId` 返回完整 trace 列表
   - `GET /api/admin/agent-trace?conversationId=N&limit=20` 返回该会话所有 message 摘要

4. **Admin 前端页面** `/admin/trace`：
   - 输入框：messageId 或 conversationId
   - 列表：每个 message 一行（时间、用户问题、token 总量、cache 命中率）
   - 点开 → 时间轴详情（van-steps / van-timeline）
   - JSON 查看器：args / output 折叠展开（syntax highlight）
   - 复制 messageId 按钮

5. **Dashboard 集成**：
   - AdminFeedbackDashboard "高 token + 低满意度案例" 加"🔍 查看 trace"按钮
   - 跳到 `/admin/trace?messageId=X`

6. **文档** `docs/agent-trace.md`：使用流程 + 限制 + 性能影响

### Out of Scope

- ❌ 实时调试（WebSocket 跟踪正在跑的 agent）—— Phase 2
- ❌ Token 用量每条都记 —— 已有 `Message.metadata.usage` 聚合够用
- ❌ LLM 输入/输出快照 —— 太大、隐私
- ❌ 跨用户 trace 关联分析 —— BI 工具范畴
- ❌ 工具性能 dashboard（avg / p50 / p99）—— 单独项目

---

## 架构

### 1. 文件结构

```
trip-server/
├── prisma/
│   ├── schema.prisma                 # +AgentStep model
│   └── migrations/                   # +add_agent_step migration
├── src/
│   ├── services/
│   │   ├── agent/
│   │   │   ├── agentEngine.ts        # +trace recorder
│   │   │   └── traceRecorder.ts      # NEW AgentStep 写入
│   │   ├── traceService.ts           # NEW 查询 trace
│   │   └── __tests__/
│   │       └── traceRecorder.test.ts # NEW 单元测试
│   ├── controllers/
│   │   └── admin.controller.ts       # +getAgentTrace
│   ├── routes/
│   │   └── admin.routes.ts           # +/admin/agent-trace
├── trip-front/
│   ├── src/
│   │   ├── api/
│   │   │   └── trace.ts              # NEW API
│   │   ├── views/
│   │   │   └── AdminTrace.vue        # NEW 时间轴页面
│   │   ├── views/
│   │   │   └── AdminFeedbackDashboard.vue  # +"查看 trace"按钮
│   │   ├── router/
│   │   │   └── index.ts              # +/admin/trace
docs/
├── agent-trace.md                    # NEW 使用文档
```

### 2. 数据流

```
agentEngine.processStream
  ↓ emit onEvent
  ↓
traceRecorder.recordStep(messageId, type, payload)
  ↓
prisma.agentStep.create({...})
  ↓ async，不阻塞 SSE 流
  ↓
用户：GET /api/admin/agent-trace?messageId=847
  ↓
traceService.getTrace(messageId) 查 prisma.agentStep
  ↓
返回 [{step: 1, type: 'tool_start', name: 'retrieve_knowledge', args: {...}}, ...]
  ↓
前端时间轴渲染
```

### 3. AgentStep 数据模型

```prisma
model AgentStep {
  id          Int      @id @default(autoincrement())
  messageId   Int      // 关联 message
  step        Int      // 1, 2, 3, ... 按时间顺序
  type        String   // 'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error'
  name        String?  // tool 名（tool_start/tool_end 用）
  args        Json?    // tool 入参（tool_start 用）
  output      String?  @db.Text  // tool 返回（tool_end 用，截断 10KB）
  durationMs  Int?     // tool 耗时（tool_end 用）
  error       String?  // 错误信息（error type 用）
  createdAt   DateTime @default(now())
  
  message     Message  @relation(fields: [messageId], references: [id], onDelete: Cascade)
  
  @@index([messageId, step])
  @@map("agent_steps")
}
```

**关键设计**：
- `output` 截断 10KB（防表膨胀）
- chunk 只计数不存（已有 SSE 流式 + message.content 完整文本）
- `onDelete: Cascade` —— message 删了 step 跟着删（与 feedback 不级联相反，因为 step 是技术性数据）
- `@@index([messageId, step])` —— 一次查询出全部 step

### 4. traceRecorder 设计

```typescript
// src/services/agent/traceRecorder.ts
class TraceRecorder {
  /** 累计一个 message 的所有 step，落 DB */
  private steps: AgentStep[] = []
  
  add(step: Omit<AgentStep, 'id' | 'createdAt'>): void {
    this.steps.push({ ...step, createdAt: new Date() })
  }
  
  async flush(messageId: number): Promise<void> {
    if (this.steps.length === 0) return
    try {
      await prisma.agentStep.createMany({ data: this.steps })
    } catch (e) {
      log.warn({ err: e, messageId, count: this.steps.length }, 'trace 落 DB 失败')
      // 不抛错 —— trace 失败不影响 agent 正常完成
    }
  }
}
```

**为什么用 buffered + flush**：
- 1 次 chat 可能 5-10 个 step，逐条 createMany N+1 问题
- 缓冲到内存，agent 完成后一次 createMany
- 失败只 warn 不影响业务

### 5. agentEngine 集成

在 `processStream` 中增加 `traceRecorder` 引用：

```typescript
private async processStream(
  executor, invokeInput, onEvent, signal,
  traceRecorder: TraceRecorder,  // NEW
) {
  // ... 现有逻辑 ...
  
  case 'on_tool_start':
    traceRecorder.add({
      messageId, step: nextStep++,
      type: 'tool_start',
      name: event.name,
      args: event.data?.input,  // LangChain 工具入参
    })
    break
    
  case 'on_tool_end':
    traceRecorder.add({
      messageId, step: nextStep++,
      type: 'tool_end',
      name: event.name,
      output: JSON.stringify(event.data?.output).slice(0, 10000),
      durationMs: Date.now() - toolStartTime,
    })
    break
    
  case 'on_chat_model_end':
    // 不写 step（已有 message.metadata.usage），但累计 chunkCount
    chunkCount++
    break
    
  case 'complete':
    traceRecorder.add({
      messageId, step: nextStep++,
      type: 'complete',
      durationMs: Date.now() - startTime,
      // 不存 usage 本身（message.metadata 已有）
    })
    traceRecorder.flush(messageId)
    break
}
```

**性能影响**：
- 1 次 chat 平均 5-10 step → 1 次 createMany
- 失败时只 warn，不影响 SSE 流

### 6. API 设计

`GET /api/admin/agent-trace/:messageId`

响应：
```json
{
  "code": 200,
  "data": {
    "messageId": 847,
    "steps": [
      { "step": 1, "type": "tool_start", "name": "retrieve_knowledge", "args": {"city":"北京","days":2}, "createdAt": "..." },
      { "step": 2, "type": "tool_end", "name": "retrieve_knowledge", "output": "5 POIs...", "durationMs": 1234, "createdAt": "..." },
      { "step": 3, "type": "complete", "durationMs": 4500, "createdAt": "..." }
    ]
  }
}
```

**404**：messageId 不存在  
**403**：非 admin

`GET /api/admin/agent-trace?conversationId=N&limit=20`

响应：conversation 内最近 20 条 message 的摘要（messageId + 简短 query + token + stepCount）

### 7. 前端 AdminTrace.vue

```
/admin/trace
  ┌──────────────────────────────────┐
  │ 输入框 [messageId ___] [查看]     │
  │ 或 会话输入 [conversationId ___]   │
  ├──────────────────────────────────┤
  │ 选中 message #847                 │
  │ 原始 query: "北京 2 天..."        │
  │ 总耗时: 4.5s | 3 chunks | 1 tool │
  ├──────────────────────────────────┤
  │ ▼ Step 时间轴                     │
  │                                   │
  │ ● 1. tool_start                   │
  │   retrieve_knowledge              │
  │   [args 展开]                     │
  │   ┌────────────────────┐          │
  │   │ {                   │          │
  │   │   "city": "北京",   │          │
  │   │   "days": 2         │          │
  │   │ }                   │          │
  │   └────────────────────┘          │
  │                                   │
  │ ● 2. tool_end                     │
  │   retrieve_knowledge (1.2s)      │
  │   [output 展开]                   │
  │   ┌────────────────────┐          │
  │   │ "5 POIs: 宽窄巷子, 锦里, ..."│ │
  │   └────────────────────┘          │
  │                                   │
  │ ● 3. complete (4.5s)              │
  └──────────────────────────────────┘
```

**实现**：
- 顶部 van-search 输入 messageId
- 中间 van-cell 列表（用消息摘要）
- 点开 → van-steps 时间轴
- args/output 用 van-collapse-item 折叠

### 8. 集成 AdminFeedbackDashboard

在"高 token + 低满意度案例"行加 "🔍 查看 trace" 按钮：

```vue
<van-button size="mini" plain @click="$router.push(`/admin/trace?messageId=${c.messageId}`)">
  🔍 Trace
</van-button>
<van-button size="mini" type="primary" plain @click="convertOne(c.feedbackId)">
  📋 转 fixture
</van-button>
```

---

## 错误处理

| 场景 | 行为 |
|---|---|
| traceRecorder.flush 失败 | warn log，不抛错（agent 业务不受影响）|
| API messageId 不存在 | 404 |
| API 非 admin | 403 |
| 输出 > 10KB | 截断 + 加 `[已截断]` 标记 |
| tool 报错 | type='error' step 存 error 字段 |
| agent 中途 abort | partial trace（缺最后 complete） |
| 大并发（100+ 同时） | createMany 批量，DB 写入压力可控（100 消息 × 10 step = 1000 行/秒） |

---

## 测试

### 1. 单元测试

- ✅ `traceRecorder.test.ts`：add/flush 顺序、flush 失败 warn、createMany 调用次数
- ✅ agentEngine 集成测试：mock prisma，验证 on_tool_start / on_tool_end / complete 各调 1 次 add

### 2. API 测试

- ✅ admin 200
- ✅ 非 admin 403
- ✅ messageId 不存在 404
- ✅ 完整 trace JSON 结构

### 3. 前端

- ✅ AdminTrace.vue 渲染测试（typecheck）
- ✅ 路由 meta.requiresAdmin 守卫

### 4. E2E

- ✅ 真实跑 chat → 检查 AgentStep 表有数据
- ✅ admin dashboard "🔍 Trace" 按钮跳到 trace 页能看完整时间轴

---

## 实施步骤

1. **DB schema + migration**（Prisma 加 AgentStep 表）
2. **traceRecorder.ts** + 单元测试
3. **agentEngine 集成**（按 step 类型 record）
4. **traceService.ts**（查询方法）
5. **API 端点**（admin 守卫 + 2 路由）
6. **前端 API + AdminTrace.vue**
7. **Dashboard 集成**（"查看 trace"按钮）
8. **实战**：跑 1 个 chat → 验证 trace 数据
9. **文档** `docs/agent-trace.md`

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 表爆炸（每个 message 5-10 step） | output 截断 10KB；chunk 不写 step；3 个月后归档策略（v2）|
| trace 失败影响主业务 | flush 失败只 warn 不抛 |
| LLM 输出快照泄露隐私 | 不存 LLM input/output（已有 message.content）|
| 数据库写入压力 | createMany 批量；后台任务清理 30 天前 trace（v2）|
| args/output 太大 | 10KB 截断 + `[已截断]` 标记 |

---

## 验证标准

1. `pnpm test` 通过（129 + 5 = 134 测试）
2. `pnpm typecheck` 双端 pass
3. 真实跑 chat → AgentStep 表 5-10 行
4. admin 调 API 200 / 非 admin 403
5. 浏览器访问 /admin/trace 看到完整时间轴
6. dashboard "🔍 Trace" 按钮跳转工作

---

## 关键决策摘要

- **中等粒度**（B 方案）：tool_start/tool_end + complete，不记 LLM 中间
- **buffer + flush** 模式：避免 N+1 写入
- **chunk 不写 step**：只累计 chunkCount 写到 complete step 的 metadata
- **不存 LLM 输入输出**：防隐私泄露 + 表膨胀
- **onDelete Cascade**：message 删了 step 跟着删（与技术数据相反于 feedback）
- **trace 失败只 warn**：不影响 agent 业务
- **/admin/trace 路由**：admin only，meta.requiresAdmin
- **集成 dashboard**："🔍 Trace" 按钮接 trace 页
