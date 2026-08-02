# API 调用错误处理机制改进方案

> 背景：基于 `trip-front/`（Vue3 + axios）与 `trip-backend/`（FastAPI）的错误处理现状分析。
> 现状短板：① 前端普通 REST 请求零重试、对 429 无感知；② 后端出站调用（高德地理编码 / Unsplash / LLM）对上游 429 未识别、未解析 `Retry-After`、无退避重访；③ 日志链路 `request-id` 未贯穿。
> 目标：补齐"重试 / 429 限流退避 / 降级兜底 / 统一日志"四块能力，且**不破坏现有 SSE 流式续传逻辑**。

---

## 一、总体改动映射

| 能力 | 现状 | 目标 | 主要改动点 |
|---|---|---|---|
| 前端 REST 重试 | ❌ 无 | ✅ 429/5xx 指数退避重试 | `trip-front/src/api/request.ts` |
| 前端 429 退避 | ❌ 无 | ✅ 解析 `Retry-After` + 兜底退避 | `request.ts` 响应拦截器 |
| 前端统一错误提示 | 散落 `message.error` | ✅ 集中 `handleApiError` + 默认兜底 | `src/utils/apiError.ts`（新建） |
| 后端出站 429 | ❌ 静默降级 | ✅ `Retry-After` 退避重访 | `src/services/http/retry.py`（新建） |
| 后端 429 应用到 geo/unsplash | ❌ | ✅ 区分 429 与 5xx | `geocode_service.py` / `unsplash_service.py` |
| `ToolResilienceWrapper` | 不认 429 | ✅ 429 纳入可重试异常 | `src/services/agent/resilience.py` |
| 日志 `request-id` | ❌ 未贯穿 | ✅ contextvars 贯穿全链路 | `main.py` + `src/utils/logger.py` |
| SSE 429 | ❌ 走"网络中断"语义 | ✅ 按 429 退避 | `request.ts` `fetchOnce` |

---

## 二、前端改进方案

### 2.1 统一重试 + 429 退避（改造 `src/api/request.ts`）

在现有响应拦截器基础上，新增重试逻辑。**仅对 429 与 5xx、网络错误、超时重试**；401 维持现有清 token + 跳登录逻辑；其余 4xx 不重试。

```ts
// request.ts —— 新增重试配置与判定
const RETRY = {
  maxRetries: 2,             // 不含首次，共 3 次
  backoffBaseMs: 1000,       // 指数退避基数
  backoffCapMs: 8000,        // 退避封顶
  retryableStatuses: [429, 500, 502, 503, 504],
}

function isRetryable(error: any): boolean {
  if (!error) return false
  if (error.code === 'ECONNABORTED' || error.message === 'Network Error') return true // 超时/网络
  const status = error.response?.status
  return status ? RETRY.retryableStatuses.includes(status) : false
}

function getRetryDelayMs(error: any, attempt: number): number {
  const status = error.response?.status
  // 429 优先使用服务端下发的 Retry-After
  if (status === 429) {
    const raw = error.response?.headers?.['retry-after']
    if (raw != null) {
      const secs = parseInt(raw, 10)
      if (!Number.isNaN(secs)) return Math.min(secs * 1000, 30000) // 封顶 30s
    }
  }
  return Math.min(RETRY.backoffBaseMs * 2 ** attempt, RETRY.backoffCapMs)
}
```

将 `post/get/put/del` 包装为带重试的版本（利用 axios 拦截器队列或闭包计数器都可以）。建议用**请求级闭包计数器**避免全局状态：

```ts
async function requestWithRetry<T>(
  fn: () => Promise<T>,
  attempt = 0,
): Promise<T> {
  try {
    return await fn()
  } catch (error: any) {
    if (!isRetryable(error) || attempt >= RETRY.maxRetries) throw error
    const delay = getRetryDelayMs(error, attempt)
    await new Promise((r) => setTimeout(r, delay))
    return requestWithRetry(fn, attempt + 1)
  }
}

export function post<T = any>(url: string, params?: any) {
  return requestWithRetry(() => request.post(url, params))
}
// get / put / del 同理
```

> ⚠️ 幂等约束：只对 `GET / PUT / DELETE` 自动重试；`POST` 非幂等（如创建行程）默认不重试，避免重复提交——可在调用处显式传 `retryablePost` 或标记 `idempotent: false`。

### 2.2 集中错误提示 + 默认兜底（新建 `src/utils/apiError.ts`）

把散落在各 `.vue` 的 `message.error('…')` 收敛为统一处理器：

```ts
import { useMessage } from 'naive-ui'
import type { ApiResponse } from '@/api/request'

const TEXT: Record<number, string> = {
  401: '登录已失效，请重新登录',
  403: '没有权限执行此操作',
  404: '请求的资源不存在',
  429: '请求过于频繁，请稍后重试',
  500: '服务暂时不可用，请稍后重试',
  502: '网关错误，请稍后重试',
  503: '服务繁忙，请稍后重试',
  504: '请求超时，请稍后重试',
}

export function handleApiError(error: any) {
  const msg = useMessage()
  const status = error?.response?.status
  const fallback = error?.response?.data?.message || error?.response?.data?.error
  msg.error(fallback || TEXT[status] || '网络异常，请稍后重试')
}

// 列表类请求的安全兜底
export function safeList<T>(resp?: ApiResponse<T[]>, fallback: T[] = []): T[] {
  return resp?.data ?? fallback
}
```

视图层改造示例：`catch (e) { handleApiError(e) }` 替代原散落 toast。

### 2.3 SSE 路径补 429 处理

`fetchStream` 的 `fetchOnce`（`request.ts:162`）目前把非 2xx 当成网络错误走"断点续传"语义。在拿 `response` 后增加 429 分支：

```ts
const response = await fetch(`/api/${url}`, { ... })
if (response.status === 429) {
  const raw = response.headers.get('Retry-After')
  const secs = raw ? parseInt(raw, 10) : NaN
  const delay = Number.isNaN(secs) ? getBackoffMs(attempt + 1) : Math.min(secs * 1000, 30000)
  throw Object.assign(new Error('rate_limited'), { retryAfter: delay })
}
```

并在 `run()` 的 `catch` 中识别 `err.retryAfter` 走退避等待（复用现有 `delayMs` 通道），**不触发断点续传**。其余网络中断逻辑保持不变。

### 2.4 日志（轻量，可选 Phase 3）

新增 `logApiError(error, { url, method })`，结构化打印 `url / status / message / timestamp`；后续可接 `/api/client-log` 上报端点。至少要替代现有零散 `console.error`。

---

## 三、后端改进方案

### 3.1 通用 429 退避包装器（新建 `src/services/http/retry.py`）

```python
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """解析 Retry-After：支持秒数或 HTTP-date。"""
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)  # 秒数
    except ValueError:
        pass
    # 可扩展解析 HTTP-date（email.utils.parsedate_to_datetime）
    return None

async def http_with_retry_on_429(
    client, method: str, url: str,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_cap: float = 30.0,
    **kwargs,
):
    """对上游 429 做指数退避 + 优先使用 Retry-After 的重试。"""
    last_resp = None
    for attempt in range(max_attempts):
        resp = await client.request(method, url, **kwargs)
        last_resp = resp
        if resp.status_code != 429:
            return resp
        delay = parse_retry_after(resp.headers.get("Retry-After"))
        if delay is None:
            delay = min(backoff_base * (2 ** attempt), backoff_cap)
        logger.warning("upstream_429", extra={"url": url, "attempt": attempt, "retry_after": delay})
        await asyncio.sleep(delay)
    return last_resp  # 最终仍 429，交由调用方降级
```

### 3.2 应用到具体出站调用

**地理编码 `geocode_service.py`**：把 `resp.raise_for_status()` 改为先判断状态码：
```python
resp = await http_with_retry_on_429(client, "GET", url, params=params)
if resp.status_code == 429:
    return None  # 或抛上游限流异常，由上层决定降级
resp.raise_for_status()  # 非 429 仍可能 5xx，保持原有降级 return None
```
**Unsplash `unsplash_service.py`**：区分 429（走退避重试）与 5xx（降级 `return []`）：
```python
resp = await http_with_retry_on_429(client, "GET", url)
if resp.status_code == 429:
    return []
resp.raise_for_status()
```

### 3.3 增强 `ToolResilienceWrapper`（`src/services/agent/resilience.py`）

让包装器能识别 HTTP 429（对 httpx 异常解析 `status_code`）：
- 新增参数 `retry_on_status: tuple = (429, 500, 502, 503, 504)`
- 当捕获异常带 `.status_code in retry_on_status` 时纳入重试；429 优先用 `Retry-After`（从异常/响应头取），否则用现有 `2 ** attempt` 退避（封顶 10s）
- **注意**：429 退避应优先尊重服务端 `Retry-After`，避免无脑 `2**attempt` 在限流时造成重试风暴

### 3.4 令牌桶自适应（可选增强 `guards.py`）

当高德 MCP 返回 429 时，不只抛 `RuntimeError("MCP 请求被限流")`，而是**临时抬高令牌获取延迟 / 收紧令牌桶**（`MCPRateLimiter` 增加 `cooldown_until` 时间戳），实现自适应限流，避免雪崩。

### 3.5 日志 `request-id` 贯穿（`main.py` + `src/utils/logger.py`）

```python
# main.py 中间件
import uuid, structlog
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=rid)
        request.state.request_id = rid
        resp = await call_next(request)
        resp.headers["X-Request-Id"] = rid
        structlog.contextvars.clear_contextvars()
        return resp
```
- 出站 httpx 请求注入 `headers["X-Request-Id"] = request.state.request_id`，便于与上游日志关联
- `structlog.contextvars` 使 `trip_log.error(..., msg=...)` 自动带 `request_id`

---

## 四、实施步骤（建议顺序）

**Phase 1（低风险、高收益，建议先做）**
1. 前端：响应拦截器加 429/5xx 重试 + `Retry-After` 解析（`request.ts`）
2. 前端：集中 `handleApiError` + `safeList` 兜底（`src/utils/apiError.ts`），替换散落 toast
3. 后端：新建 `http_with_retry_on_429`，应用到 `geocode_service.py` / `unsplash_service.py`

**Phase 2（增强）**
4. 后端：`ToolResilienceWrapper` 支持 429 退避
5. 后端：`request-id` 链路贯通日志
6. 前端：SSE `fetchStream` 补 429 分支

**Phase 3（可选）**
7. 前端统一日志上报
8. 后端高德 MCP 自适应限流

---

## 五、风险与注意

- **重试放大 / 雪崩**：429 时必须优先使用 `Retry-After` 并设上限（30s），禁止在限流期间无脑指数退避；客户端应有总体重试预算（如 `maxRetries=2`）。
- **幂等性**：POST 非幂等请求（创建行程、提交反馈）默认不自动重试，仅在调用处显式开启。
- **退避封顶**：所有退避设上限（前端 8–30s，后端 10–30s），避免长尾延迟拖垮用户体验。
- **不破坏现有行为**：SSE 断点续传、后端入站 429/503 守卫、主备 LLM 切换保持不变，新逻辑只做"增量"。
- **可观测性**：重试与限流事件务必打日志（含 url/status/attempt），便于后续调参。

---

## 六、实施状态

### ✅ Phase 1（已提交）
- 后端 `src/services/http/retry.py`：`http_with_retry_on_429`（优先 `Retry-After`，指数兜底封顶 30s，最多 3 次）
- 后端 `geocode_service.py` / `unsplash_service.py`：接入 429 退避重试，区分 429（退避）与 5xx（降级）
- 前端 `src/api/request.ts`：`post/get/put/del` 包重试；429 可重试（含 POST），超时/5xx 仅幂等重试；429 优先 `Retry-After`（封顶 30s）
- 前端 `src/utils/apiError.ts`：`getApiErrorText` / `handleApiError` / `safeList`
- 前端 `src/views/Detail.vue`：作为采用示例

### ✅ Phase 2（已提交）
- 后端 `src/services/agent/resilience.py`：`ToolResilienceWrapper._compute_backoff` 支持上游 429（优先 `Retry-After` 封顶 30s），其余指数退避封顶 10s
- 后端 `src/utils/logger.py`：processors 增加 `structlog.contextvars.merge_contextvars`
- 后端 `src/main.py`：新增原生 ASGI `RequestIDMiddleware`（生成/透传 `x-request-id`，绑定 structlog 上下文，响应头回写，兼容 SSE 不缓冲）
- 后端 `src/services/http/retry.py`：`request_id_headers()` 出站调用携带 `X-Request-Id`；`geocode_service.py` / `unsplash_service.py` 已注入
- 前端 `src/api/request.ts`：`fetchStream` 增加连接级 429 / 5xx 分支（`UpstreamRateLimit` / `UpstreamServerError`），按退避重连，不触发断点续传语义；新增 `waitWithAbort`
- 前端 `Chat.vue` / `TokenUsage.vue` / `History.vue` / `Profile.vue`：catch 块统一改用 `handleApiError(error, message)`，Chat 流式 `onError` 直接展示服务端消息（含 429）

### ⬜ Phase 3（可选，未做）
- 前端统一日志上报（接入 Sentry / 上报接口）
- 后端高德 MCP 自适应限流（基于 `Retry-After` / 令牌桶动态调节）

### 验证
- 后端：改动文件 `py_compile` 通过
- 前端：`vue-tsc -b` 全量类型检查通过，**本次改动未引入新类型错误**（项目原有 22 处历史类型告警不属本次范围）
- 两项改动均已 commit 并 push 至 `origin/main`
