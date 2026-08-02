# Agent 可视化调试工具 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全链路 agent step 持久化 + 检索 API + 可视化时间轴页面，让 admin 能回放任何一次 agent 决策过程。

**Architecture:** 新增 AgentStep 表，agentEngine 用 buffer+flush 模式在每个 tool/complete 步骤落 DB；admin API 查 trace；AdminTrace.vue 时间轴 + JSON 折叠。dashboard 高 token 案例行加"🔍 Trace"按钮。

**Tech Stack:** Node.js + Prisma + Express + Vue 3 / Vant + vitest

---

## 文件结构

```
trip-server/
├── prisma/
│   └── schema.prisma                          # +AgentStep model
├── src/
│   ├── services/
│   │   ├── agent/
│   │   │   ├── agentEngine.ts                 # +trace recorder 集成
│   │   │   └── traceRecorder.ts               # NEW buffer + flush
│   │   ├── traceService.ts                    # NEW 查询方法
│   │   └── __tests__/
│   │       ├── traceRecorder.test.ts          # NEW 单元测试
│   │       └── agentEngine.test.ts            # +trace 集成测试
│   ├── controllers/
│   │   └── admin.controller.ts                # +getAgentTrace
│   └── routes/
│       └── admin.routes.ts                    # +/admin/agent-trace
trip-front/
└── src/
    ├── api/
    │   └── trace.ts                           # NEW API
    ├── views/
    │   ├── AdminTrace.vue                     # NEW 时间轴页面
    │   └── AdminFeedbackDashboard.vue         # +"🔍 Trace"按钮
    └── router/
        └── index.ts                           # +/admin/trace
docs/
├── agent-trace.md                             # NEW 使用文档
└── agent-improvements.md                      # UPDATE 标 done
```

---

## Task 1: Prisma schema + migration

**Files:**
- Modify: `trip-server/prisma/schema.prisma`

- [ ] **Step 1: 在 schema.prisma 末尾加 AgentStep model**

```prisma
model AgentStep {
  id          Int      @id @default(autoincrement())
  messageId   Int
  step        Int
  type        String   // 'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error'
  name        String?
  args        Json?
  output      String?  @db.Text
  durationMs  Int?
  error       String?
  createdAt   DateTime @default(now())
  
  message     Message  @relation(fields: [messageId], references: [id], onDelete: Cascade)
  
  @@index([messageId, step])
  @@map("agent_steps")
}
```

- [ ] **Step 2: 在 Message model 加反向关联**

找到 `model Message` 块，加：
```prisma
  steps        AgentStep[]
```

- [ ] **Step 3: 推 migration**

```bash
cd /Users/wang/Documents/trip/trip-server && npx prisma db push
```

Expected: 创建 agent_steps 表

- [ ] **Step 4: 重新生成 Prisma client**

```bash
npx prisma generate
```

- [ ] **Step 5: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/prisma/schema.prisma
git commit -m "feat(db): add AgentStep table for agent execution trace

  - Fields: messageId + step + type + name/args/output/durationMs/error
  - Index on (messageId, step) for fast trace retrieval
  - OnDelete Cascade (technical data, not user content)
  - Output truncated 10KB to prevent table bloat"
```

---

## Task 2: traceRecorder.ts 核心

**Files:**
- Create: `trip-server/src/services/agent/traceRecorder.ts`
- Create: `trip-server/src/services/__tests__/traceRecorder.test.ts`

- [ ] **Step 1: 写 traceRecorder.ts**

```typescript
/**
 * Agent Step Trace Recorder
 *
 * 把 agent 决策过程（tool 调用、step 耗时）落 DB，方便 admin 回放。
 *
 * 设计：
 * - buffer 模式：每个 step add 到内存（避免 N+1 DB 写入）
 * - flush 模式：agent 完成后一次 createMany
 * - 失败只 warn，不影响 agent 业务
 * - 同一 messageId 的 step 顺序由调用方保证
 */

import prisma from '../../config/database'
import { agentLog as log } from '../../utils/logger'

export interface StepInput {
  step: number
  type: 'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error'
  name?: string
  args?: Record<string, any>
  output?: string
  durationMs?: number
  error?: string
}

export class TraceRecorder {
  private messageId: number
  private steps: StepInput[] = []

  constructor(messageId: number) {
    this.messageId = messageId
  }

  add(step: StepInput): void {
    this.steps.push(step)
  }

  /** 写入 DB。失败只 warn，不抛错。 */
  async flush(): Promise<void> {
    if (this.steps.length === 0) return
    const data = this.steps.map((s) => ({
      messageId: this.messageId,
      step: s.step,
      type: s.type,
      name: s.name ?? null,
      args: s.args ? (s.args as any) : null,
      output: s.output ?? null,
      durationMs: s.durationMs ?? null,
      error: s.error ?? null,
    }))
    try {
      await prisma.agentStep.createMany({ data })
      log.info({ messageId: this.messageId, count: this.steps.length }, 'agent trace 落 DB')
    } catch (e) {
      log.warn({ err: e, messageId: this.messageId, count: this.steps.length }, 'agent trace 落 DB 失败')
    }
  }

  /** 测试用：拿当前已 buffer 的 steps */
  getSteps(): readonly StepInput[] {
    return this.steps
  }
}
```

- [ ] **Step 2: 写单元测试**

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { TraceRecorder } from '../agent/traceRecorder'

// Mock prisma
const mockCreateMany = vi.fn()
vi.mock('../../config/database', () => ({
  default: {
    agentStep: {
      createMany: (...args: any[]) => mockCreateMany(...args),
    },
  },
}))

describe('TraceRecorder', () => {
  beforeEach(() => {
    mockCreateMany.mockReset()
    mockCreateMany.mockResolvedValue({ count: 0 })
  })

  it('add() 累积 step 到 buffer', () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_start', name: 'retrieve_knowledge' })
    r.add({ step: 2, type: 'tool_end', name: 'retrieve_knowledge', output: '5 POIs', durationMs: 1234 })
    expect(r.getSteps()).toHaveLength(2)
  })

  it('flush() 空 buffer 不调 createMany', async () => {
    const r = new TraceRecorder(847)
    await r.flush()
    expect(mockCreateMany).not.toHaveBeenCalled()
  })

  it('flush() 调 createMany 一次传所有 step', async () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_start', name: 'retrieve_knowledge', args: { city: '北京' } })
    r.add({ step: 2, type: 'tool_end', name: 'retrieve_knowledge', output: '5 POIs', durationMs: 1234 })
    r.add({ step: 3, type: 'complete', durationMs: 4500 })
    await r.flush()
    expect(mockCreateMany).toHaveBeenCalledTimes(1)
    expect(mockCreateMany.mock.calls[0][0].data).toHaveLength(3)
    expect(mockCreateMany.mock.calls[0][0].data[0]).toMatchObject({
      messageId: 847,
      step: 1,
      type: 'tool_start',
      name: 'retrieve_knowledge',
      args: { city: '北京' },
    })
  })

  it('args null 时不传 args 字段', async () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'chunk' })
    await r.flush()
    expect(mockCreateMany.mock.calls[0][0].data[0].args).toBeNull()
  })

  it('flush 失败只 warn，不抛错', async () => {
    mockCreateMany.mockRejectedValue(new Error('DB down'))
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_start' })
    await expect(r.flush()).resolves.toBeUndefined()  // 不抛
  })

  it('output 截断由调用方负责，recorder 透传', async () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_end', output: 'a'.repeat(15000) })
    await r.flush()
    expect(mockCreateMany.mock.calls[0][0].data[0].output).toBe('a'.repeat(15000))  // 透传
  })
})
```

- [ ] **Step 3: 跑测试验证通过**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm test src/services/__tests__/traceRecorder.test.ts
```
Expected: 6 tests pass

- [ ] **Step 4: Commit**

```bash
git add trip-server/src/services/agent/traceRecorder.ts trip-server/src/services/__tests__/traceRecorder.test.ts
git commit -m "feat(trace): traceRecorder (buffer + flush)

  - add() 累积 step 到内存
  - flush() 一次 createMany 写所有 step
  - 失败只 warn 不抛错
  - 6 unit tests"
```

---

## Task 3: agentEngine 集成 trace recorder

**Files:**
- Modify: `trip-server/src/services/agent/agentEngine.ts`

- [ ] **Step 1: 读 agentEngine.ts 找 on_chat_model_stream / on_tool_start / on_tool_end / complete 位置**

```bash
grep -n "on_chat_model_stream\|on_tool\|on_chat_model_end\|type: 'complete'" /Users/wang/Documents/trip/trip-server/src/services/agent/agentEngine.ts
```

- [ ] **Step 2: 加 import**

```typescript
import { TraceRecorder } from './traceRecorder'
```

- [ ] **Step 3: 在 processStream 函数签名加 traceRecorder 参数**

找到 `private async processStream(` 位置，加 `traceRecorder: TraceRecorder,` 到参数列表末尾。

- [ ] **Step 4: 在每个 LangChain 事件处加 trace step**

参考 `event.event` switch 块：

```typescript
// on_chat_model_stream
} else if (event.event === 'on_chat_model_stream') {
  // 不写 step（chunk 太多），只累计
  chunkCount++
}

// on_tool_start
} else if (event.event === 'on_tool_start') {
  const toolName = event.name || 'unknown'
  toolStartTimes.set(toolName, Date.now())
  traceRecorder.add({
    step: stepCounter++,
    type: 'tool_start',
    name: toolName,
    args: event.data?.input as Record<string, any> | undefined,
  })
  await onEvent({ type: 'tool_start', name: toolName })
}

// on_tool_end
} else if (event.event === 'on_tool_end') {
  const toolName = event.name || 'unknown'
  const startTime = toolStartTimes.get(toolName)
  const durationMs = startTime ? Date.now() - startTime : undefined
  toolStartTimes.delete(toolName)
  const output = event.data?.output !== undefined
    ? JSON.stringify(event.data.output).slice(0, 10000)
    : undefined
  traceRecorder.add({
    step: stepCounter++,
    type: 'tool_end',
    name: toolName,
    output,
    durationMs,
  })
  await onEvent({ type: 'tool_end', name: toolName })
}
```

**注意**：具体行号需根据现有代码调整。先 `cat` 看下当前结构。

- [ ] **Step 5: 在 complete 处加 step + flush**

找到 `await onEvent({ type: 'complete', ... })` 附近，加：

```typescript
  traceRecorder.add({
    step: stepCounter++,
    type: 'complete',
    durationMs: Date.now() - streamStartTime,
  })
  await traceRecorder.flush()
  await onEvent({ type: 'complete', content: result.content, usage: result.usage })
```

- [ ] **Step 6: 在 error 路径加 step + flush**

找到 error 处理代码，加：

```typescript
  traceRecorder.add({
    step: stepCounter++,
    type: 'error',
    error: errMsg,
  })
  await traceRecorder.flush()
  await onEvent({ type: 'error', error: errMsg })
```

- [ ] **Step 7: 在 invoke() 函数最顶部创建 TraceRecorder**

```typescript
const traceRecorder = new TraceRecorder(messageId)
```

把 traceRecorder 传给 processStream 调用。

- [ ] **Step 8: typecheck**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm typecheck
```

- [ ] **Step 9: 跑测试看是否破坏现有**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm test
```

Expected: 129 + 6 (traceRecorder) = 135 pass。如果 agentEngine 测试有需要 traceRecorder 的失败，先看下能否加 mock。

- [ ] **Step 10: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/src/services/agent/agentEngine.ts
git commit -m "feat(trace): agentEngine 集成 trace recorder

  - 新增 TraceRecorder 参数贯穿 processStream
  - on_tool_start: 写 tool_start step（含 args）
  - on_tool_end: 写 tool_end step（含 output 截断 10KB + durationMs）
  - on_chat_model_stream: 不写 step（防表爆炸），只累计 chunkCount
  - complete: 写 complete step + flush
  - error: 写 error step + flush
  - 失败 flush 只 warn 不影响业务"
```

---

## Task 4: traceService 查询方法

**Files:**
- Create: `trip-server/src/services/traceService.ts`

- [ ] **Step 1: 写 traceService.ts**

```typescript
/**
 * Agent Trace 查询 Service
 *
 * admin 看 agent 决策过程用
 */

import prisma from '../config/database'

export interface TraceStep {
  id: number
  step: number
  type: string
  name: string | null
  args: Record<string, any> | null
  output: string | null
  durationMs: number | null
  error: string | null
  createdAt: string
}

class TraceService {
  /**
   * 查单个 message 的完整 trace（按 step 升序）
   */
  async getTraceByMessage(messageId: number): Promise<TraceStep[]> {
    const steps = await prisma.agentStep.findMany({
      where: { messageId },
      orderBy: { step: 'asc' },
      select: {
        id: true,
        step: true,
        type: true,
        name: true,
        args: true,
        output: true,
        durationMs: true,
        error: true,
        createdAt: true,
      },
    })
    return steps.map((s) => ({
      ...s,
      createdAt: s.createdAt.toISOString(),
    }))
  }

  /**
   * 查某会话最近 N 条 message 的 trace 摘要（admin dashboard 用）
   */
  async getTraceSummaryByConversation(conversationId: number, limit = 20) {
    const messages = await prisma.message.findMany({
      where: { conversationId, role: 'assistant' },
      orderBy: { createdAt: 'desc' },
      take: limit,
      select: {
        id: true,
        content: true,
        metadata: true,
        createdAt: true,
        _count: { select: { steps: true } },
      },
    })
    return messages.map((m) => {
      const meta = m.metadata as { usage?: { prompt: number; completion: number; total: number; cached: number } } | null
      return {
        messageId: m.id,
        preview: m.content.slice(0, 100),
        stepCount: m._count.steps,
        usage: meta?.usage ?? null,
        createdAt: m.createdAt.toISOString(),
      }
    })
  }

  /**
   * 单 message 的元数据 + step 数量（trace 页面头部用）
   */
  async getMessageMetadata(messageId: number) {
    const msg = await prisma.message.findUnique({
      where: { id: messageId },
      select: {
        id: true,
        role: true,
        content: true,
        metadata: true,
        createdAt: true,
        conversationId: true,
        _count: { select: { steps: true } },
      },
    })
    if (!msg) return null
    return {
      ...msg,
      createdAt: msg.createdAt.toISOString(),
    }
  }
}

export const traceService = new TraceService()
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/traceService.ts
git commit -m "feat(trace): traceService with 3 query methods

  - getTraceByMessage: 完整 step 列表（按 step 升序）
  - getTraceSummaryByConversation: 会话最近 N 条 message 摘要 + stepCount
  - getMessageMetadata: 单 message 元数据 + step 数"
```

---

## Task 5: API 端点

**Files:**
- Modify: `trip-server/src/controllers/admin.controller.ts`（或创建新文件）
- Modify: `trip-server/src/routes/admin.routes.ts`（或新文件）

- [ ] **Step 1: 检查现有 admin controller/route 文件结构**

```bash
ls /Users/wang/Documents/trip/trip-server/src/controllers/
ls /Users/wang/Documents/trip/trip-server/src/routes/
```

如果有 `admin.controller.ts` / `admin.routes.ts`，加到那里。如果没有，新建文件。

- [ ] **Step 2: 加 controller 方法**

```typescript
  /**
   * admin: 单 message 完整 trace
   * GET /api/admin/agent-trace/:messageId
   */
  getAgentTrace = async (req: Request, res: Response, next: NextFunction) => {
    try {
      if (req.user!.roleId !== 1) {
        return res.status(403).json({ code: 403, error: '仅管理员可访问' })
      }
      const messageId = parseInt(req.params.messageId, 10)
      if (isNaN(messageId)) {
        return res.status(400).json({ code: 400, error: 'messageId 必填且为数字' })
      }
      const message = await traceService.getMessageMetadata(messageId)
      if (!message) {
        return res.status(404).json({ code: 404, error: 'message 不存在' })
      }
      const steps = await traceService.getTraceByMessage(messageId)
      res.json({ code: 200, data: { message, steps } })
    } catch (e) {
      next(e)
    }
  }

  /**
   * admin: 会话最近 trace 摘要
   * GET /api/admin/agent-trace?conversationId=N&limit=20
   */
  getAgentTraceSummary = async (req: Request, res: Response, next: NextFunction) => {
    try {
      if (req.user!.roleId !== 1) {
        return res.status(403).json({ code: 403, error: '仅管理员可访问' })
      }
      const conversationId = parseInt(req.query.conversationId as string, 10)
      const limit = Math.min(parseInt((req.query.limit as string) || '20', 10), 100)
      if (isNaN(conversationId)) {
        return res.status(400).json({ code: 400, error: 'conversationId 必填且为数字' })
      }
      const summaries = await traceService.getTraceSummaryByConversation(conversationId, limit)
      res.json({ code: 200, data: { summaries } })
    } catch (e) {
      next(e)
    }
  }
```

**注意**：按项目现有 controller 模式调整（`next` vs 内联 try/catch）。

- [ ] **Step 3: 加 route**

```typescript
router.get('/admin/agent-trace/:messageId', authMiddleware, adminController.getAgentTrace)
router.get('/admin/agent-trace', authMiddleware, adminController.getAgentTraceSummary)
```

- [ ] **Step 4: typecheck**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add trip-server/src/controllers/ trip-server/src/routes/
git commit -m "feat(trace): GET /api/admin/agent-trace/{:messageId, ?conversationId}"
```

---

## Task 6: 前端 API + AdminTrace.vue 页面

**Files:**
- Create: `trip-front/src/api/trace.ts`
- Create: `trip-front/src/views/AdminTrace.vue`
- Modify: `trip-front/src/router/index.ts`

- [ ] **Step 1: 写 api/trace.ts**

```typescript
import request from './request'

export interface TraceStep {
  id: number
  step: number
  type: string
  name: string | null
  args: Record<string, any> | null
  output: string | null
  durationMs: number | null
  error: string | null
  createdAt: string
}

export interface TraceMessage {
  id: number
  role: string
  content: string
  metadata: any
  createdAt: string
  conversationId: number
  _count: { steps: number }
}

export async function fetchAgentTrace(messageId: number): Promise<{ message: TraceMessage; steps: TraceStep[] }> {
  const res = await request.get<{ code: number; data: { message: TraceMessage; steps: TraceStep[] } }>(
    `/api/admin/agent-trace/${messageId}`
  )
  return res.data.data
}

export interface TraceSummary {
  messageId: number
  preview: string
  stepCount: number
  usage: { prompt: number; completion: number; total: number; cached: number } | null
  createdAt: string
}

export async function fetchAgentTraceSummary(conversationId: number, limit = 20): Promise<TraceSummary[]> {
  const res = await request.get<{ code: number; data: { summaries: TraceSummary[] } }>(
    `/api/admin/agent-trace?conversationId=${conversationId}&limit=${limit}`
  )
  return res.data.data.summaries
}
```

- [ ] **Step 2: 写 AdminTrace.vue**

```vue
<template>
  <div class="admin-trace">
    <van-nav-bar title="Agent Trace" left-text="返回" left-arrow @click-left="$router.back()" />
    
    <div class="search-bar">
      <van-field v-model.number="searchMessageId" label="Message ID" type="number" placeholder="输入 messageId" />
      <van-button type="primary" size="small" @click="loadTrace">查看</van-button>
    </div>
    
    <div class="search-bar">
      <van-field v-model.number="searchConvId" label="Conversation ID" type="number" placeholder="输入 conversationId 查列表" />
      <van-button type="primary" size="small" @click="loadSummary">查列表</van-button>
    </div>
    
    <div v-if="traceMessage" class="trace-detail">
      <van-cell-group>
        <van-cell title="Message ID" :value="String(traceMessage.id)" />
        <van-cell title="Role" :value="traceMessage.role" />
        <van-cell title="Steps" :value="String(traceMessage._count.steps)" />
        <van-cell title="Created" :value="traceMessage.createdAt" />
        <van-cell title="Content">
          <template #value>
            <div class="content-preview">{{ traceMessage.content.slice(0, 300) }}</div>
          </template>
        </van-cell>
      </van-cell-group>
      
      <h3>Step 时间轴</h3>
      <van-steps direction="vertical" :active="traceSteps.length - 1">
        <van-step v-for="step in traceSteps" :key="step.id">
          <h4>{{ step.step }}. {{ step.type }}<span v-if="step.name">: {{ step.name }}</span></h4>
          <div v-if="step.durationMs !== null" class="meta">耗时: {{ step.durationMs }}ms</div>
          <div v-if="step.error" class="error">Error: {{ step.error }}</div>
          <van-collapse v-if="step.args || step.output">
            <van-collapse-item v-if="step.args" title="args" :name="`args-${step.id}`">
              <pre class="json">{{ JSON.stringify(step.args, null, 2) }}</pre>
            </van-collapse-item>
            <van-collapse-item v-if="step.output" title="output" :name="`output-${step.id}`">
              <pre class="json">{{ step.output }}</pre>
            </van-collapse-item>
          </van-collapse>
        </van-step>
      </van-steps>
    </div>
    
    <div v-else-if="traceSummary.length > 0" class="summary-list">
      <h3>会话 #{{ searchConvId }} 最近消息</h3>
      <van-cell
        v-for="s in traceSummary"
        :key="s.messageId"
        :title="`#${s.messageId} · ${s.stepCount} steps`"
        :label="s.preview"
        is-link
        @click="() => { searchMessageId = s.messageId; loadTrace() }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { fetchAgentTrace, fetchAgentTraceSummary, type TraceStep, type TraceMessage, type TraceSummary } from '@/api/trace'

const searchMessageId = ref<number | null>(null)
const searchConvId = ref<number | null>(null)
const traceMessage = ref<TraceMessage | null>(null)
const traceSteps = ref<TraceStep[]>([])
const traceSummary = ref<TraceSummary[]>([])

async function loadTrace() {
  if (!searchMessageId.value) return
  const result = await fetchAgentTrace(searchMessageId.value)
  traceMessage.value = result.message
  traceSteps.value = result.steps
  traceSummary.value = []
}

async function loadSummary() {
  if (!searchConvId.value) return
  traceMessage.value = null
  traceSteps.value = []
  traceSummary.value = await fetchAgentTraceSummary(searchConvId.value)
}

// 自动从 URL query 加载
import { useRoute } from 'vue-router'
const route = useRoute()
if (route.query.messageId) {
  searchMessageId.value = parseInt(route.query.messageId as string, 10)
  loadTrace()
}
</script>

<style scoped>
.admin-trace { padding: 16px; }
.search-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.content-preview { font-size: 12px; color: #666; max-width: 200px; word-break: break-all; }
.json { background: #f5f5f5; padding: 8px; border-radius: 4px; font-size: 12px; overflow-x: auto; }
.meta { color: #999; font-size: 12px; }
.error { color: red; font-size: 12px; }
h3 { margin: 16px 0 8px; }
h4 { margin: 0 0 4px; font-size: 14px; }
</style>
```

- [ ] **Step 3: 加路由**

在 `trip-front/src/router/index.ts` 加：

```typescript
{
  path: '/admin/trace',
  name: 'AdminTrace',
  component: () => import('@/views/AdminTrace.vue'),
  meta: { requiresAuth: true, requiresAdmin: true },
}
```

- [ ] **Step 4: typecheck**

```bash
cd /Users/wang/Documents/trip/trip-front && pnpm typecheck
```

- [ ] **Step 5: Commit**

```bash
git add trip-front/src/api/trace.ts trip-front/src/views/AdminTrace.vue trip-front/src/router/index.ts
git commit -m "feat(trace): AdminTrace.vue timeline page

  - Search by messageId or conversationId
  - Time-axis view (van-steps) for each step
  - JSON viewer (van-collapse) for args/output
  - Route: /admin/trace (meta.requiresAdmin)
  - Auto-load from ?messageId=X query"
```

---

## Task 7: Dashboard 集成 "🔍 Trace" 按钮

**Files:**
- Modify: `trip-front/src/views/AdminFeedbackDashboard.vue`

- [ ] **Step 1: 在"高 token + 低满意度案例"行加按钮**

在已有的 "📋 转 fixture" 按钮旁加：

```vue
<van-button
  size="mini"
  plain
  @click="$router.push(`/admin/trace?messageId=${c.messageId}`)"
>
  🔍 Trace
</van-button>
```

- [ ] **Step 2: typecheck**

```bash
cd /Users/wang/Documents/trip/trip-front && pnpm typecheck
```

- [ ] **Step 3: Commit**

```bash
git add trip-front/src/views/AdminFeedbackDashboard.vue
git commit -m "feat(trace): admin dashboard '🔍 Trace' button

  - 在'高 token + 低满意度案例'行加按钮
  - 跳到 /admin/trace?messageId=X
  - AdminTrace.vue 自动从 query 加载"
```

---

## Task 8: 实战验证

**Files:**
- (no new files, just E2E test)

- [ ] **Step 1: 跑 chat 生成 trace**

```bash
cd /Users/wang/Documents/trip/trip-server
nohup pnpm dev > /tmp/trace-e2e.log 2>&1 &
sleep 8

TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"eval-test","password":"EvalTest@2026"}' | jq -r .data.token)

# 跑 chat（带 RAG 工具调用）
curl -s -X POST http://localhost:3000/api/trip/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"成都 3 天美食行程"}' | head -50

# 等 agent 完成
sleep 5
```

- [ ] **Step 2: 查最新 messageId 的 trace**

```bash
MESSAGE_ID=$(node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.message.findFirst({
  where: { role: 'assistant' },
  orderBy: { id: 'desc' },
  select: { id: true }
}).then((m) => { console.log(m.id); p.\$disconnect(); });
")

echo "Latest message ID: $MESSAGE_ID"
curl -s "http://localhost:3000/api/admin/agent-trace/$MESSAGE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.data | {message: .message.id, stepCount: (.steps | length), steps: [.steps[] | {step, type, name, durationMs}]}'
```

Expected: 看到 `retrieve_knowledge` tool 调用 + complete step

- [ ] **Step 3: 测非 admin 403**

```bash
# 改 roleId=2
node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.user.update({ where: { username: 'eval-test' }, data: { roleId: 2 } })
  .then(() => p.\$disconnect());
"

# 重启服务
pkill -f "nodemon.*trip-server" || true
nohup pnpm dev > /tmp/trace-e2e.log 2>&1 &
sleep 8

TOKEN2=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"eval-test","password":"EvalTest@2026"}' | jq -r .data.token)

curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://localhost:3000/api/admin/agent-trace/$MESSAGE_ID" \
  -H "Authorization: Bearer $TOKEN2"
```

Expected: `HTTP 403`

- [ ] **Step 4: 还原 roleId=1**

```bash
node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.user.update({ where: { username: 'eval-test' }, data: { roleId: 1 } })
  .then(() => p.\$disconnect());
"
pkill -f "nodemon.*trip-server" || true
```

- [ ] **Step 5: 检查 agent_steps 表有数据**

```bash
node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.agentStep.count().then((n) => { console.log('AgentStep 总数:', n); p.\$disconnect(); });
"
```

Expected: > 0

- [ ] **Step 6: Commit (无新文件，可选 commit 一个 trace 数据小记)**

可选：跑一个 eval 把 trace 当 fixture 验证防回归。不强制。

---

## Task 9: 文档

**Files:**
- Create: `docs/agent-trace.md`
- Modify: `docs/agent-improvements.md`（标 §2.2 部分完成）

- [ ] **Step 1: 写 docs/agent-trace.md**

```markdown
# Agent Trace 可视化调试

> 配套 `docs/agent-improvements.md` §2.2

## 目标

让 admin 能在浏览器**回放任何一次 agent 决策过程**——RAG 召回的工具、工具输入参数、工具返回、step 耗时、最终回复。

## 数据流

\`\`\`
agentEngine.processStream
  ↓
traceRecorder.add() 到内存
  ↓
agent complete / error 时 flush()
  ↓
prisma.agentStep.createMany() 一次写所有 step
  ↓
GET /api/admin/agent-trace/:messageId
  ↓
AdminTrace.vue 时间轴渲染
\`\`\`

## 使用方式

### 1. Admin Trace 页面

1. 登录 admin → /admin/trace
2. 输入 messageId 或 conversationId
3. 选中 message → 时间轴详情

### 2. 从 Dashboard 跳转

在 admin dashboard "高 token + 低满意度案例" 行点 "🔍 Trace" → 直接跳到该 message 的 trace 页。

### 3. API

\`\`\`bash
# 单 message 完整 trace
GET /api/admin/agent-trace/:messageId

# 会话最近 20 条 message 摘要
GET /api/admin/agent-trace?conversationId=N&limit=20
\`\`\`

Admin only (roleId=1)，否则 403。

## AgentStep 数据模型

\`\`\`prisma
model AgentStep {
  id          Int
  messageId   Int
  step        Int          // 1, 2, 3...
  type        String       // tool_start | tool_end | chunk | complete | error
  name        String?      // tool 名
  args        Json?        // 工具入参
  output      String?      // 工具返回（截断 10KB）
  durationMs  Int?         // 工具耗时
  error       String?      // 错误信息
  createdAt   DateTime
}
\`\`\`

**关键设计**：
- chunk 只累计数量不写 step（防表爆炸）
- output 截断 10KB
- onDelete Cascade（与技术数据相反于 feedback）
- `@@index([messageId, step])` 一次查询出全部

## 性能影响

- 1 次 chat 平均 5-10 step → 1 次 createMany
- flush 失败只 warn，不影响 agent 业务
- 100 消息/秒 × 10 step = 1000 行/秒 DB 写入（MySQL 轻松）

## 限制

- **不存 LLM 输入/输出**（隐私 + 表大小）
- **chunk 不写 step**（已有 SSE 流 + message.content 完整文本）
- **不存中间 thought**（同 LLM 输出理由）
- **表归档**（v2）：30 天前 trace 自动清理

## 验证

\`\`\`bash
# 单元测试
pnpm test
# 129 (前) + 6 (traceRecorder) = 135

# E2E
pnpm dev  # 启服务
# 跑 chat → 查 trace → 看时间轴
\`\`\`

## 关键设计决策

1. **buffer + flush**：避免 N+1
2. **中等粒度**：只记 tool + complete（不记 LLM 中间）
3. **chunk 不写 step**：防表爆炸
4. **onDelete Cascade**：与技术数据一致
5. **trace 失败只 warn**：不影响业务
6. **不存 LLM 输入/输出**：隐私
\`\`\`

### 2. Update `docs/agent-improvements.md`

找到 §2.2 可观测性，加注：

```markdown
> ✅ **部分完成 2026-06-25**：agent trace 持久化（AgentStep 表 + admin 可视化时间轴页面）。完整 OpenTelemetry 待后续。
```

### 3. Commit

```bash
cd /Users/wang/Documents/trip
git add docs/agent-trace.md docs/agent-improvements.md
git commit -m "docs: agent-trace usage guide + mark §2.2 partial done"
```

---

## 验证清单

跑完所有 Task 后，最终检查：

- [ ] `pnpm test` 通过（129 + 6 = 135 测试）
- [ ] `pnpm typecheck` 双端 pass
- [ ] AgentStep 表创建成功
- [ ] 真实跑 chat → agent_steps 有数据
- [ ] admin 调 API 200 / 非 admin 403
- [ ] 浏览器 /admin/trace 看到完整时间轴
- [ ] dashboard "🔍 Trace" 按钮跳转工作
- [ ] `docs/agent-trace.md` 完整

## 总 commit 清单

1. `feat(db): add AgentStep table`
2. `feat(trace): traceRecorder (buffer + flush)`
3. `feat(trace): agentEngine integration`
4. `feat(trace): traceService query methods`
5. `feat(trace): admin API endpoints`
6. `feat(trace): AdminTrace.vue + API`
7. `feat(trace): dashboard '🔍 Trace' button`
8. `docs: agent-trace usage guide`
