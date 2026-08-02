# Streamable Agent 断点续传 — 设计文档

> **版本**：v1.0
> **作者**：项目 owner
> **状态**：✅ **Phase 1 已交付**（Day 1-7 全部完成）
> **目标**：让 AI 流式输出支持"断点续传"——客户端断开后能从断点继续

---

## 0. 交付状态（2026-06-24 更新）

### Phase 1 全部完成

| 阶段 | 状态 | commit | 关键交付 |
|---|---|---|---|
| Day 1-2 | ✅ | b853530 + 9627396 | Redis 客户端 + streamStore（17 测试） + CI service container |
| Day 3-4 | ✅ | d9e82f9 | ResumableStream helper + Controller Last-Event-ID + IDOR 防护 |
| Day 5-6 | ✅ | 7d5d72d | 前端 SSEParser + 自动重连 + Chat.vue UI 提示 |
| Day 7 | ✅ | (本 commit) | demo HTML + 端到端验证 + 文档 |

### 测试覆盖
- 后端：103/103 测试通过（含 17 streamStore + 15 ResumableStream + 1 id 字段）
- 前端：19/19 SSEParser 测试通过（node:test）
- typecheck：双端 clean
- 端到端 e2e：手动验证通过，**字节级一致**（4 chunks 续传内容与原始完全相同）

### 实际部署经验
- **SSE `id:` 字段**：用本地 `localSeq` 计数器（同步 +1），与 Redis INCR 异步配合。单线程 send 调用保证一致性
- **fire-and-forget Redis 写**：`appendEvent` 不阻塞 SSE 流，但失败时只能 log warn（不重试）
- **TTL 续期**：每次 append 刷新 3 个 key 的 TTL（stream/{id} + events + seq），活跃流永不过期
- **重连退避**：1s/2s/4s/8s/16s 封顶，5 次上限。`retryDelaysMs` 可注入（demo 用 [10,10,10,10,10] 跳过退避加速测试）
- **降级路径**：Redis 不可用时 `getStreamId()` 返回 null，前端拿不到 streamId 就**不重连**（直接报错），避免无限重试浪费流量
- **IDOR 防护**：`resumeStream` 内部 `state.userId === req.user.userId` 校验，**即使 controller 忘记检查也兜底**——这是 P0 级安全门
- **错误码映射**：自定义错误类（StreamNotFoundError / StreamForbiddenError / StreamBadRequestError），controller 用 `instanceof` 映射 404/403/400

### 已知设计权衡（Phase 2 待优化）
- **server 主动 abort agent**：client socket 关闭时 `req.on('close')` 触发 abort，**重连拿到的是 abort 前的 event**。如需"server 端继续跑 + 客户端断网重连拿到完整内容"，需延迟 abort（10-30s 窗口），属 Phase 2
- **INCR + RPUSH 非原子**：极端情况下（进程崩溃在 INCR 后 RPUSH 前）seq 跳号。Phase 2 用 Lua 脚本原子化
- **错误类型用 Error 基类**：未做自定义类型扩展（`error.code` 字段），Phase 2 加

### 演示
打开 `docs/resumable-demo.html`（配合后端 3000 端口）即可完整体验：
1. 登录（eval-test 账号）
2. 发送消息 → 看到流式输出
3. 点"模拟断网" → fetchStream 自动触发重连
4. 看到状态栏显示"重连中 (1/5)..."
5. 成功续传（实际生产场景受 server abort 限制，见上）

---

## 1. 背景与动机

### 1.1 当前实现的痛点

项目当前 SSE 流式实现的代码片段（`trip-front/src/api/request.ts:60`）：

```typescript
const response = await fetch(`/api/${url}`, { ... })
const reader = response.body.getReader()
while (true) {
  const { done, value } = await reader.read()
  if (done) break
  // ... 处理 chunk
}
```

服务端代码片段（`trip-server/src/controllers/trip.controller.ts:62`）：

```typescript
const { conversationId: newConvId } = await tripService.chatStream({
  userId, message, conversationId, signal,
  callbacks: { onChunk, onToolStart, onToolEnd },
})
```

**问题**：
- ❌ 客户端刷新页面 → **整段回复丢失**
- ❌ 网络切换（WiFi ↔ 4G）→ 中断
- ❌ 浏览器崩溃 → 整段重传
- ❌ LLM 还在跑 / 工具还没返回 → 用户体验"白等"

### 1.2 真实场景影响

| 用户场景 | 痛点 |
|---|---|
| 3-5 分钟的长行程规划 | 收到 80% 时网络波动 → 整段重头，浪费 2 分钟 + 大量 token |
| 移动端使用 | 切换网络频繁，体验割裂 |
| 多工具调用 | 工具执行耗时 5-10s，用户等待焦虑 |
| 调试 | 看不到"已经生成了什么"，不知道是死锁还是慢 |

### 1.3 设计目标

| 指标 | 当前 | 目标 |
|---|---|---|
| 客户端断线后能否续传 | ❌ 不能 | ✅ 从断点继续 |
| 重复 chunk 浪费 | 100% 重传 | 0% 重复 |
| 工具调用时断开 | 整个 agent 重启 | ✅ 工具结果复用 |
| 网络切换 | 中断 | ✅ 无感切换 |
| 服务端压力（重连） | 全量重算 | ✅ 仅续推未发 chunk |

---

## 2. SSE 协议标准能力

**好消息**：SSE 协议本身支持断点续传，但**很多实现没启用**。

### 2.1 SSE 标准字段

```
id: 42
event: chunk
data: {"type":"chunk","content":"成都"}

id: 43
event: chunk
data: {"type":"chunk","content":"3天"}

id: 44
event: complete
data: {"conversationId":206}
```

**关键字段**：
- `id:` —— 事件唯一标识（任意字符串）
- `event:` —— 事件类型（默认 `message`）
- `data:` —— 数据载荷
- `retry:` —— 客户端重连间隔（毫秒）

### 2.2 客户端自动重连（`EventSource`）

浏览器原生 `EventSource` API：
- 自动重连（指数退避）
- 自动带 `Last-Event-ID` 头（值为**最后收到**的 `id:`）
- 服务端读取这个头就知道客户端"收到哪了"

**关键点**：`EventSource` 是只读的 GET 请求，**不适合 POST 场景**（POST 需要 body）。

---

## 3. 设计方案

### 3.1 总览

```
┌──────────┐                              ┌──────────┐
│ Browser  │                              │ Server   │
│          │  1. POST /api/trip/chat      │          │
│          │ ───────────────────────────→ │          │
│          │ ←─────── SSE chunk 1 (id=1)  │ agent    │
│          │ ←─────── SSE chunk 2 (id=2)  │ execute  │
│          │ ←─────── SSE chunk 3 (id=3)  │          │
│          │                              │          │
│          │   2. 网络断开 8 秒           │          │
│          │                              │          │
│          │  3. 重连 POST + Last-Event-ID: 3
│          │ ───────────────────────────→ │
│          │                              │ 读取 Last-Event-ID=3
│          │                              │ 找到 chunk 4-未发送的
│          │ ←─────── SSE chunk 4 (id=4)  │ 续推
│          │ ←─────── SSE chunk 5 (id=5)  │
│          │ ←─────── complete (id=N)     │
└──────────┘                              └──────────┘
```

### 3.2 两层设计

#### 第一层：协议层（必须有）
- 服务端：每个 SSE 事件加 `id:` 字段（sequence_id）
- 客户端：带 `Last-Event-ID` 头重连
- 服务端：识别 Last-Event-ID，从断点续推

**这一层解决"断点续传"**。

#### 第二层：状态层（进阶）
- 服务端：把每次 chunk 写 DB（持久化）
- 客户端：重连时先读历史 chunk（增量）
- 服务端：agent 内部状态可恢复

**这一层解决"agent 状态可恢复"**。

### 3.3 推荐实施路径

```
Phase 1 (MVP):
  协议层 + 内存存储 sequence_id
  ↓
Phase 2 (进阶):
  协议层 + DB 持久化
  ↓
Phase 3 (高级):
  agent 状态机 + 中断恢复
```

**Phase 1 预计 1 周**，Phase 2/3 各 1 周。**先做 Phase 1**。

---

## 4. Phase 1 详细设计（推荐先做）

### 4.1 协议约定

#### 服务端 SSE 输出

每个事件加 `id:` 字段（sequence_id，单调递增）：

```
id: 1
event: tool_start
data: {"type":"tool_start","name":"retrieve_knowledge"}

id: 2
event: chunk
data: {"type":"chunk","content":"好的"}

id: 3
event: chunk
data: {"type":"chunk","content"，"根据你"}

id: 4
event: tool_end
data: {"type":"tool_end","name":"retrieve_knowledge"}

...

id: 100
event: complete
data: {"conversationId":206}
```

**sequence_id 规则**：
- 单调递增（同一 conversation 内）
- 全局唯一
- 类型：Long / Snowflake（避免 int 溢出）

#### 客户端重连请求

```
POST /api/trip/chat
Authorization: Bearer xxx
Content-Type: application/json
Last-Event-ID: 3

{
  "message": "...",
  "conversationId": 206
}
```

**`Last-Event-ID`** 是浏览器 EventSource 标准头。但 fetch API 不自动带——需要客户端**手动加**。

### 4.2 服务端实现

#### 核心数据结构

```typescript
/**
 * 内存中的"流状态"
 * 同一 conversationId 可能有多次 agent 调用（一次 ask 一次）
 * 用 streamId 区分每次调用
 */
interface StreamState {
  streamId: string            // UUID
  conversationId: number
  userId: number
  message: string
  events: Array<{             // 累积所有事件
    seq: number
    type: string
    data: any
  }>
  status: 'running' | 'completed' | 'error' | 'aborted'
  abortController: AbortController
  createdAt: number
  lastEventAt: number
}
```

#### Stream 状态机

```
created ──→ running ──→ completed
              ↓
            aborted
              ↓
            error
```

#### 续传逻辑

```typescript
function resumeFrom(clientLastSeq: number, stream: StreamState): SSEEvent[] {
  // 找到 clientLastSeq 之后的所有 events
  return stream.events.filter(e => e.seq > clientLastSeq)
}
```

**关键边界**：
1. **agent 还在跑（status=running）** → 续推剩余 events
2. **agent 已完成（status=completed）** → 推完结标记即可
3. **agent 异常（status=error）** → 推错误事件
4. **客户端的 lastSeq 是未来值**（client 收到过未来的 seq）→ 全部重推
5. **客户端的 lastSeq 太老**（超过 TTL）→ 拒绝续传，让客户端重新开始

### 4.3 内存存储 vs DB 存储

| 方案 | 优点 | 缺点 |
|---|---|---|
| **内存 Map<streamId, StreamState>** | 简单、快 | 服务重启会丢，水平扩展需要 sticky session |
| **Redis** | 持久化、跨实例 | 多一次网络调用 |
| **MySQL + 序列号表** | 持久化、与业务数据同库 | 写性能有压力 |

**Phase 1 推荐**：内存 Map，加 TTL（如 10 分钟自动清理）。

**Phase 2 升级**：Redis 持久化。

### 4.4 客户端实现

#### 为什么不用 EventSource？

EventSource 只能 GET，**无法 POST body**。我们需要发 `message`。

#### 自实现 fetch + 重连

```typescript
async function fetchStreamWithResume(
  url: string,
  body: any,
  onEvent: (evt: SSEEvent) => void,
  onError: (e: any) => void,
): Promise<AbortController> {
  let lastEventId = 0
  const controller = new AbortController()
  
  const connect = async () => {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Last-Event-ID': String(lastEventId),  // 关键
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        
        // 解析 SSE 事件
        let sepIdx
        while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIdx)
          buffer = buffer.slice(sepIdx + 2)
          
          // 解析 id: 字段
          const idMatch = rawEvent.match(/^id: (\d+)/m)
          if (idMatch) {
            lastEventId = parseInt(idMatch[1])
          }
          
          // 解析 data: 字段
          for (const line of rawEvent.split('\n')) {
            if (line.startsWith('data:')) {
              const data = JSON.parse(line.substring(5).trimStart())
              onEvent(data)
            }
          }
        }
      }
    } catch (e) {
      if (e.name === 'AbortError') return  // 用户主动取消
      onError(e)
      // 关键：非 abort 错误 → 等待后重连
      setTimeout(() => connect(), 1000)  // 1s 后重试
    }
  }
  
  connect()
  return controller
}
```

**关键点**：
- `Last-Event-ID` 头每次请求都带最新值
- `id:` 解析后更新 lastEventId
- 断开后自动重连（指数退避）

### 4.5 服务端代码改造

#### 创建 SSE helper

```typescript
// utils/stream.ts 新增
interface ResumableStreamContext {
  streamId: string
  events: Array<{ seq: number; type: string; data: any }>
  seqCounter: number
}

export function createResumableStream(
  res: Response,
  streamId: string,
  initialLastEventId: number,
  events: Array<...>,
): { send: (type, data) => void; end: () => void; resumeFrom: (lastId) => void } {
  // ... 完整实现见 Phase 1 实施
}
```

#### controller 改造

```typescript
export const chat = async (req: Request, res: Response) => {
  const { message, conversationId } = req.body
  const lastEventId = Number(req.headers['last-event-id']) || 0  // 关键
  
  // 检查 stream 状态
  const streamState = streamStore.get(streamId)
  if (streamState) {
    // 续传
    return resumeStream(res, streamState, lastEventId)
  }
  
  // 全新开始
  // ... 原逻辑
}
```

---

## 5. 边界与异常处理

### 5.1 边界列表

| # | 边界 | 处理 |
|---|---|---|
| 1 | agent 还在跑时断开 | 续传时只推未发 events，不重启 agent |
| 2 | 工具调用中（5-10s）断开 | 服务端继续等工具结果，客户端重连时直接拿结果 |
| 3 | 客户端重复接收（同 seq 出现 2 次） | 客户端按 seq 去重 |
| 4 | seq 间隙（漏了 seq=5） | 服务端补发（必须推连续 seq） |
| 5 | 服务端重启（内存丢） | 返回 410 Gone，客户端从头开始 |
| 6 | 客户端 lastSeq 超出 TTL | 返回 410 Gone，客户端从头开始 |
| 7 | 客户端 lastSeq 超过当前最大 seq | 服务端已经是"未来"，全部重推 |
| 8 | 用户取消（AbortController） | 不重连，正常清理 |

### 5.2 测试用例

```typescript
describe('SSE 断点续传', () => {
  it('客户端收到 3 个 chunk 后断开，重连从第 4 个开始', async () => {
    // 模拟
  })
  
  it('客户端断开时 agent 正在调工具，重连后直接拿工具结果', async () => {
    // 模拟
  })
  
  it('客户端 lastSeq > 最大 seq，全部重推', async () => {
    // 模拟
  })
  
  it('服务端重启后客户端重连，返回 410 Gone', async () => {
    // 模拟
  })
  
  it('客户端重复接收同 seq 事件，按 seq 去重', async () => {
    // 模拟
  })
})
```

---

## 6. 数据结构详细设计

### 6.1 服务端 StreamState

```typescript
// 内存存储（Phase 1）
const streamStore = new Map<string, StreamState>()

interface StreamState {
  streamId: string         // UUID
  conversationId: number
  userId: number
  message: string          // 触发这次流的消息
  events: StreamEvent[]    // 已生成的所有 events
  status: 'running' | 'completed' | 'error' | 'aborted'
  abortController: AbortController
  createdAt: number
  expiresAt: number        // createdAt + TTL
}

interface StreamEvent {
  seq: number              // 单调递增
  type: 'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error' | 'heartbeat'
  data: any                // 原始数据
}
```

### 6.2 TTL 与清理

```typescript
const STREAM_TTL_MS = 10 * 60 * 1000  // 10 分钟

// 定期清理过期 stream
setInterval(() => {
  const now = Date.now()
  for (const [id, state] of streamStore) {
    if (state.expiresAt < now) {
      streamStore.delete(id)
    }
  }
}, 60 * 1000)  // 每分钟扫一次
```

### 6.3 streamId 传递

服务端创建 stream 时生成 UUID，**通过 `X-Stream-Id` 响应头告诉客户端**：

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
X-Stream-Id: 7f3e8a90-1234-5678-9abc-def012345678

id: 1
event: tool_start
data: ...
```

客户端重连时**带 X-Stream-Id**（或者用 conversationId + 创建时间推断）。

更简单：直接用 `conversationId` 作为 key（一次 chat 一个 stream）。但**多轮对话里同一 conversationId 会有多个 stream**——所以用 streamId 更稳。

---

## 7. 与现有代码的对接

### 7.1 后端现有调用链

```
HTTP POST /api/trip/chat
  ↓
tripController.chat (src/controllers/trip.controller.ts:26)
  ↓
tripService.chatStream (src/services/tripService.ts:18)
  ↓
agentEngine.chat (src/services/agent/agentEngine.ts)
  ↓
SSE events
```

### 7.2 改造点

#### 1. `utils/stream.ts` 新增 ResumableStream

```typescript
// 新增 createResumableStream() 函数
// 兼容 createStreamResponse() 接口
```

#### 2. `controllers/trip.controller.ts` 改造

```typescript
export const chat = async (req, res) => {
  const lastEventId = Number(req.headers['last-event-id']) || 0
  const streamId = req.headers['x-stream-id'] as string | undefined
  
  // 检查是否能续传
  if (streamId) {
    const existing = streamStore.get(streamId)
    if (existing) {
      return resumeExistingStream(res, existing, lastEventId)
    }
  }
  
  // 全新开始（原有逻辑）
  // ...
}
```

#### 3. `services/agent/agentEngine.ts` 改造

`streamEvents({version:'v2'})` 的 callback 加 `seq` 字段：

```typescript
let seq = 0
onEvent: async (event) => {
  seq++
  // 持久化 + 推送
  streamState.events.push({ seq, type: event.type, data: event })
  res.write(`id: ${seq}\n`)
  res.write(`event: ${event.type}\n`)
  res.write(`data: ${JSON.stringify(event)}\n\n`)
}
```

#### 4. 前端 `api/request.ts` fetchStream 改造

加 `Last-Event-ID` 头 + 解析 `id:` + 自动重连。

---

## 8. 性能与可靠性

### 8.1 内存占用

- 一次 chat 平均 100 events × 200 字节 = 20KB
- 10 分钟 TTL，假设 QPS 5 → 5 × 10 × 60 = 3000 stream × 20KB = 60MB
- **可接受**（加 LRU 限制 1000 stream ≈ 20MB）

### 8.2 并发安全

```typescript
// 同一 streamId 的 events 数组需要线程安全
// Node.js 单线程 + 事件循环 → 数组 push 安全
// 但有边界：响应已 end 时再 push 会抛错
```

### 8.3 水平扩展

Phase 1 内存存储 → **单实例**。多实例需要：
- Sticky session（同一用户路由到同一实例）
- 或 Phase 2 升级到 Redis 共享

### 8.4 监控指标

```
- stream_resume_total: 续传次数
- stream_resume_success_rate: 续传成功率
- avg_resume_gap_ms: 平均续传间隔
- stream_state_size: 当前 stream 数
```

---

## 9. 实施计划（Phase 1）

### 9.1 Day 1-2：服务端基础

- [ ] 设计 `StreamState` 接口
- [ ] 实现 `streamStore` 内存 Map + TTL 清理
- [ ] 在 `agentEngine.chat` 加 sequence_id 计数
- [ ] 在 SSE 输出加 `id:` 字段
- [ ] 单元测试：sequence_id 单调递增

### 9.2 Day 3-4：服务端续传逻辑

- [ ] `controllers/trip.controller.ts` 读取 `Last-Event-ID` 头
- [ ] 实现 `resumeExistingStream()` 函数
- [ ] 单元测试：续传 3 个边界（运行中 / 已完成 / 已过期）

### 9.3 Day 5-6：客户端改造

- [ ] `api/request.ts` fetchStream 加 Last-Event-ID
- [ ] 实现 `id:` 字段解析
- [ ] 实现自动重连（指数退避）
- [ ] 单元测试：客户端重连逻辑

### 9.4 Day 7：端到端 + 文档

- [ ] e2e 测试：断网模拟 → 重连 → 续传
- [ ] 写 demo 脚本
- [ ] 更新 docs
- [ ] 录 5 分钟 demo 视频

---

## 10. Phase 2 预告（可选）

### 10.1 Redis 持久化

```typescript
// stream events 存 Redis
// key: stream:${streamId}:events
// type: list
// value: JSON.stringify({ seq, type, data })
// TTL: 10 分钟
```

### 10.2 agent 状态机

- 把 agent 当前状态（"等 LLM / 等工具 / 整合中"）持久化
- 客户端重连时，能从"等 LLM 中"状态恢复
- 复杂但价值高

### 10.3 流式压缩

- 用 gzip 压缩 SSE events
- 带宽节省 50%+

---

## 11. 风险评估

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| 内存占用过高 | 中 | 服务 OOM | LRU + 数量限制 |
| seq 溢出（int32） | 低 | 续传失败 | 用 Long（53 位） |
| 重连风暴 | 中 | 服务压力 | 指数退避 + 限流 |
| 多实例不一致 | 中（生产） | 续传失败 | Sticky session 或 Redis |
| 客户端兼容性 | 低 | 部分浏览器无法用 | 检测 + fallback |

---

## 12. 评审结论（2026-06-22）

### 12.1 决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | 存储 | **Redis 持久化** | 多实例、跨重启、可观测 |
| 2 | TTL | 10 分钟 | 流式平均 30s，10 分钟足够 5 次重试 |
| 3 | 客户端 | **fetch + 自实现重连** | EventSource 不支持 POST body |
| 4 | streamId 传递 | **X-Stream-Id 头** | 干净、不污染 URL |
| 5 | sequence_id | int（53 位内） | Snowflake 过度工程 |
| 6 | Phase 1 范围 | **仅 chunk 续传** | agent 状态恢复 → Phase 2 |

### 12.2 Phase 1 / Phase 2 分工

**Phase 1（1 周）**：
- Redis 存 chunks（seq → event 映射）
- SSE 加 `id:` 字段
- 客户端 Last-Event-ID 重连
- **不支持**：agent 中断后从断点继续执行（重连时只续推未发 chunks，后续 agent 执行从头开始）

**Phase 2（1 周）**：
- agent 状态机持久化
- 工具调用幂等
- LLM 调用可恢复

### 12.3 Phase 1 范围细化

**客户端重连行为**：
1. 客户端收到 chunk seq=1, 2, 3 后断开
2. 重连时带 Last-Event-ID: 3
3. **情况 A（agent 还在跑）**：服务端推 seq=4, 5, ...，agent 继续执行
4. **情况 B（agent 已完成）**：服务端推完结事件，客户端收到 complete
5. **情况 C（agent 重启了）**：服务端从头生成新 stream（返回 410 Gone），客户端从头开始

**情况 A/B 完美**——**情况 C 是 fallback**。

### 12.4 Phase 1 不做的事情

- ❌ agent 重启后从断点继续（agent 整个重新跑）
- ❌ 工具调用幂等（重复调用会有副作用）
- ❌ LLM 调用恢复（重复调 LLM 会重新计费）

这些都放 Phase 2。Phase 1 价值已经够面试讲。

---

## 13. 实施命令

设计已定。开始写代码前请确认：

1. ✅ Redis 已在本地或测试环境运行？
2. ✅ `redis` Node 客户端已装？
3. ✅ 项目使用 pino 日志，添加 `pinoRedis`?
4. ✅ Phase 1 7 天计划确认？

确认后进入 Day 1 实施（服务端 Redis 存储层 + sequence_id）。
