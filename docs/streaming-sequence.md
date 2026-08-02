# 流式响应时序图（SSE 可续传）

> 覆盖：正常流式、Redis 双写、断点续传、重试/退避。
> 关键文件：`trip-front/src/api/request.ts`、`trip-front/src/api/stream-parser.ts`、
> `trip-backend/src/controllers/chat_controller.py`、`trip-backend/src/utils/stream.py`、
> `trip-backend/src/services/trip_service.py`、`trip-backend/src/services/stream_store.py`、
> `trip-backend/src/middleware/concurrency_guard.py`

## 1. 正常流式响应（含 Redis 双写）

```mermaid
sequenceDiagram
    autonumber
    participant UI as Chat.vue / TripGenerating.vue
    participant FS as fetchStream (request.ts)
    participant P as SSEParser
    participant MW as 后端中间件链
    participant C as chat_controller.chat
    participant R as create_resumable_stream
    participant S as trip_service.chat_stream
    participant A as agent_engine + LLM
    participant ST as stream_store (Redis/内存)
    participant SR as StreamingResponse

    UI->>FS: "fetchStream('/trip/chat', {message}, onChunk…)"
    FS->>MW: "POST /api/trip/chat (Authorization, Content-Type)"
    MW->>MW: "auth → rate_limit → token_budget → concurrency_guard.try_acquire"
    alt 并发/限流超限
        MW-->>FS: "429 (Retry-After)"
        FS-->>UI: "退避后重试 / onError"
    else 通过
        MW->>C: "转发请求"
    end

    C->>R: "create_resumable_stream(user_id, conv_id, source=chat_stream)"
    R->>ST: "create_stream(user_id, conv_id)"
    ST-->>R: "streamId = stream:{uuid}"
    R-->>C: "yield stream_meta {streamId}"
    C-->>FS: "SSE 响应头 + X-Stream-Id: stream:{uuid}"
    FS->>FS: "闭包保存 streamId (lastSeq=0)"

    R->>S: "await source (chat_stream 生成器)"
    S->>S: "建/取 conversation，存 user msg，预建 assistant msg"
    S->>A: "asyncio.shield(run_agent) + 事件循环读 queue"
    A->>A: "LLM 流式 → on_event(chunk/tool_start/tool_end)"

    loop 每个增量事件
        A-->>S: "queue.put(event)"
        S-->>R: "yield {type:chunk, content} / tool_*"
        R->>ST: "append_event(seq, type, payload) (best-effort 双写)"
        R-->>SR: "SSE: id: n\ndata: {…}"
        SR-->>FS: "chunk 字节流"
        FS->>P: "feed(chunk)"
        P-->>FS: "parseSSEEvent → ev (ev.id=lastSeq)"
        FS-->>UI: "onChunk(content) / onToolEvent"
    end

    Note over S,FS: "每 ~15s 无事件 → yield {type:heartbeat} → onHeartbeat"

    A-->>S: "queue.put(__done__, usage)"
    S-->>R: "yield {type:complete, data:{conversationId, usage}}"
    R->>ST: "mark_complete(streamId) (best-effort)"
    R-->>SR: "event: end / complete"
    SR-->>FS: "流结束"
    FS-->>UI: "onComplete(data); completed=true"
    C->>C: "_stream_with_release.finally → release 并发信号量"
```

## 2. 断点续传（网络中断 → 带 X-Stream-Id + Last-Event-ID 重连）

```mermaid
sequenceDiagram
    autonumber
    participant FS as fetchStream (request.ts)
    participant P as SSEParser
    participant MW as 后端中间件链
    participant C as chat_controller.chat
    participant RS as resume_stream
    participant ST as stream_store
    participant SR as StreamingResponse

    Note over FS,SR: "正常流式进行中，客户端已持有 streamId + lastSeq"

    SR--xFS: "网络中断 (reader.read() 抛错)"
    Note over FS: "completed=false 且 已有 streamId → 进入网络中断续传分支"
    FS->>FS: "attempt++; onResume(attempt,max); waitWithAbort(backoff)"

    FS->>MW: "POST /api/trip/chat 带 X-Stream-Id + Last-Event-ID: lastSeq"
    MW->>C: "转发请求"

    alt Last-Event-ID 非法
        C-->>FS: "SSE error (400): 必须是非负整数"
    else 续传路径
        C->>RS: "resume_stream(streamId, lastSeq, user_id)"
        RS->>ST: "get_stream_state(streamId)"
        ST-->>RS: "state {userId, status, totalSeq}"
        alt stream 不存在
            RS-->>C: "StreamNotFoundError → 404"
        else 不属于当前用户 (IDOR)
            RS-->>C: "StreamForbiddenError → 403"
        else lastSeq 超界
            RS-->>C: "StreamBadRequestError → 400"
        else 校验通过
            RS->>ST: "get_events_since(streamId, lastSeq)"
            ST-->>RS: "缺失 events (seq>lastSeq)"
        end
    end

    RS-->>SR: "重发 events (id 接续) + event: end"
    SR-->>FS: "SSE 字节流"
    FS->>P: "feed(chunk)"
    P-->>FS: "parseSSEEvent → 更新 lastSeq"
    FS-->>FS: "onChunk 补齐缺失内容 → onComplete"

    Note over FS,ST: "即使客户端断连，Agent 因 asyncio.shield 继续跑，<br/>事件持续写入 stream_store，续传可拿到全部数据"
```

## 3. 重试与退避（429 / 5xx / 网络中断 / 其他 4xx）

```mermaid
sequenceDiagram
    autonumber
    participant FS as fetchStream.run()
    participant Srv as 后端
    participant UI as Chat.vue

    FS->>Srv: "fetchOnce() 发起流式请求"

    alt 连接级 429 (Retry-After)
        Srv-->>FS: "HTTP 429, err.name=UpstreamRateLimit"
        alt attempt < maxRetries
            FS->>FS: "delay(Retry-After 或退避); attempt++; onResume"
            FS->>FS: "递归 run() 重连 (不需 streamId)"
        else 超限
            FS-->>UI: "onError('请求过于频繁')"
        end

    else 连接级 5xx
        Srv-->>FS: "HTTP 500/502/503/504, err.name=UpstreamServerError"
        alt attempt < maxRetries
            FS->>FS: "delay(退避); attempt++; onResume; run()"
        else 超限
            FS-->>UI: "onError('服务暂时不可用')"
        end

    else 其他 4xx (如 401)
        Srv-->>FS: "err.name=UpstreamError"
        FS-->>UI: "onError (不可重试)"

    else 网络中断 (AbortError 除外)
        Srv--xFS: "连接断开"
        alt 已有 streamId
            FS->>FS: "delay(退避); attempt++; onResume"
            FS->>Srv: "带 X-Stream-Id + Last-Event-ID 续传"
        else 无 streamId
            FS-->>UI: "onError('网络中断，且服务端未下发 streamId')"
        end

    else 用户主动停止
        FS->>FS: "controller.abort() → AbortError"
        FS-->>UI: "直接返回，不重连"
    end
```

## 核心机制速记

| 机制 | 实现 | 文件 |
|------|------|------|
| SSE 双写 | 边 yield 边 `append_event` 到 Redis（best-effort） | `utils/stream.py:117-124` |
| 可续传 id | 首包下发 `X-Stream-Id`，每条带 `id: n` | `utils/stream.py:108-117` |
| 续传校验 | IDOR 校验 owner + lastSeq 越界判定 | `utils/stream.py:163-185` |
| 断连保护 | `asyncio.shield(run_agent)`，断连后 Agent 继续写 Store | `trip_service.py:242` |
| Redis 降级 | 不可用则内存 dict（同进程可续传） | `stream_store.py:119-128` |
| 并发守卫 | 流式端点 `finally` 释放信号量 | `concurrency_guard.py:46-53` |
| 前端退避 | 429 优先 `Retry-After`，其余指数退避 | `request.ts:305-358` |
