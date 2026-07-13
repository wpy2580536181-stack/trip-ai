import axios from 'axios'
import { SSEParser, getBackoffMs, type StreamEvent } from './stream-parser'

const request = axios.create({
  baseURL: '/api',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json',
  },
})

request.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('userInfo')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * Python 后端使用的两种响应格式：
 *
 * Format A（仅 /api/trip/recommend, /api/trip/optimize）:
 *   { success: boolean, data?: T, error?: string }
 *
 * Format B（所有其他端点）:
 *   { code: number, data?: T, message?: string, error?: string }
 */

export interface ApiResponseFormatA<T = any> {
  success: boolean
  data?: T
  error?: string
}

export interface ApiResponseFormatB<T = any> {
  code: number
  data?: T
  message?: string
  error?: string
}

export type ApiResponse<T = any> = ApiResponseFormatA<T> | ApiResponseFormatB<T>

// ---------------------------------------------------------------------------
// 重试 + 429 退避（Phase 1 改进）
// ---------------------------------------------------------------------------
const RETRY_CONFIG = {
  maxRetries: 2, // 不含首次，共 3 次
  backoffBaseMs: 1000,
  backoffCapMs: 8000,
  serverErrorStatuses: [500, 502, 503, 504] as const,
}

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE'

/**
 * 判断该错误是否可重试。
 * - 429：限流被拒，服务端尚未处理，可安全重试（含 POST）
 * - 超时 / 网络异常（ECONNABORTED / Network Error）：仅幂等方法（非 POST）重试，
 *   避免 POST 非幂等请求在已部分处理时被重复提交
 * - 5xx：仅幂等方法重试
 */
function isRetryable(error: any, method: HttpMethod): boolean {
  if (!error) return false

  if (error.code === 'ECONNABORTED' || error.message === 'Network Error') {
    return method !== 'POST'
  }

  const status = error.response?.status
  if (!status) return false

  if (status === 429) return true
  if ((RETRY_CONFIG.serverErrorStatuses as readonly number[]).includes(status)) {
    return method !== 'POST'
  }
  return false
}

/**
 * 计算退避等待时间（毫秒）。
 * - 429 优先使用服务端下发的 Retry-After（秒），封顶 30s
 * - 其余可重试错误：指数退避 1s → 2s → 4s（封顶 backoffCapMs）
 */
function getRetryDelayMs(error: any, attempt: number): number {
  const status = error.response?.status
  if (status === 429) {
    const raw = error.response?.headers?.['retry-after']
    if (raw != null) {
      const secs = parseInt(raw, 10)
      if (!Number.isNaN(secs)) return Math.min(secs * 1000, 30000)
    }
  }
  return Math.min(RETRY_CONFIG.backoffBaseMs * 2 ** attempt, RETRY_CONFIG.backoffCapMs)
}

async function requestWithRetry<T>(
  method: HttpMethod,
  fn: () => Promise<T>,
  attempt = 0,
): Promise<T> {
  try {
    return await fn()
  } catch (error: any) {
    if (!isRetryable(error, method) || attempt >= RETRY_CONFIG.maxRetries) throw error
    const delay = getRetryDelayMs(error, attempt)
    await new Promise<void>((resolve) => setTimeout(resolve, delay))
    return requestWithRetry(method, fn, attempt + 1)
  }
}

export function post<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return requestWithRetry('POST', () => request.post(url, params))
}

export function get<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return requestWithRetry('GET', () => request.get(url, { params }))
}

export function put<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return requestWithRetry('PUT', () => request.put(url, params))
}

export function del<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return requestWithRetry('DELETE', () => request.delete(url, { params }))
}

/**
 * 断点续传流式请求选项
 */
export interface FetchStreamOptions {
  /** 最大重试次数（不含首次），默认 5 */
  maxRetries?: number
  /** 自定义退避时间（覆盖默认 1s/2s/4s/8s/16s） */
  retryDelaysMs?: number[]
}

export async function fetchStream(
  url: string,
  data?: any,
  onChunk?: (chunk: string) => void,
  onComplete?: (data?: any) => void,
  onError?: (error: any) => void,
  onToolEvent?: (type: string, name: string) => void,
  onHeartbeat?: () => void,
  onResume?: (attempt: number, maxRetries: number) => void,
  options?: FetchStreamOptions,
): Promise<AbortController> {
  const controller = new AbortController()
  const maxRetries = options?.maxRetries ?? 5
  const retryDelays = options?.retryDelaysMs

  // 续传状态（闭包内跨重试保持）
  let streamId: string | null = null
  let lastSeq: number = 0
  let attempt = 0
  let completed = false // 收到 event: end 后置 true

  const token = localStorage.getItem('token')
  const baseHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) {
    baseHeaders['Authorization'] = `Bearer ${token}`
  }

  /**
   * 处理单条 SSE 事件
   * 返回 true 表示应该停止（complete / error / 用户 abort）
   */
  const handleEvent = (ev: StreamEvent): boolean => {
    // 记录 lastSeq（用于续传）
    if (ev.id !== undefined) lastSeq = ev.id

    if (ev.isEnd) {
      onComplete?.(ev.data)
      completed = true
      return true
    }

    if (ev.type === 'chunk') {
      onChunk?.(ev.content)
    } else if (ev.type === 'complete') {
      onComplete?.(ev.data)
      completed = true
      return true
    } else if (ev.type === 'error') {
      onError?.(ev.error || '流式数据解析异常')
      completed = true
      return true
    } else if (ev.type === 'tool_start' || ev.type === 'tool_end') {
      onToolEvent?.(ev.type, ev.name || '')
    } else if (ev.type === 'heartbeat') {
      onHeartbeat?.()
    }
    return false
  }

  /**
   * 单次 fetch + 流式读取
   * 抛出非 AbortError 错误表示"网络中断"
   */
  const fetchOnce = async (): Promise<void> => {
    const headers = { ...baseHeaders }
    if (streamId) {
      headers['X-Stream-Id'] = streamId
      if (lastSeq > 0) headers['Last-Event-ID'] = String(lastSeq)
    }

    const response = await fetch(`/api/${url}`, {
      method: 'POST',
      body: JSON.stringify(data),
      headers,
      signal: controller.signal,
    })

    // Phase 2：连接级错误（非网络错误）识别，避免进入"网络中断续传"分支
    if (response.status === 429) {
      const raw = response.headers.get('Retry-After')
      let retryAfterMs: number | undefined
      if (raw) {
        const secs = parseInt(raw, 10)
        if (!Number.isNaN(secs)) retryAfterMs = Math.min(secs * 1000, 30000)
      }
      const err: any = new Error('请求过于频繁（429）')
      err.name = 'UpstreamRateLimit'
      err.retryAfterMs = retryAfterMs
      throw err
    }
    if (response.status >= 500 && response.status < 600) {
      const err: any = new Error(`服务暂时不可用（${response.status}）`)
      err.name = 'UpstreamServerError'
      throw err
    }
    if (!response.ok) {
      const err: any = new Error(`请求失败（${response.status}）`)
      err.name = 'UpstreamError'
      err.status = response.status
      throw err
    }

    // 解析 X-Stream-Id header（仅首次请求有）
    const responseStreamId = response.headers.get('X-Stream-Id')
    if (responseStreamId) streamId = responseStreamId

    if (!response.body) throw new Error('Response body is null')

    const reader = response.body.getReader()
    const parser = new SSEParser()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = new TextDecoder().decode(value, { stream: true })
      const events = parser.feed(chunk)
      for (const ev of events) {
        if (handleEvent(ev)) {
          // 收到 end / error：取消 reader
          try { await reader.cancel() } catch { /* ignore */ }
          return
        }
      }
    }
  }

  /**
   * 等待退避（同时监听 abort，避免退避期间阻塞取消）
   */
  const waitWithAbort = (ms: number): Promise<void> =>
    new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, ms)
      controller.signal.addEventListener(
        'abort',
        () => {
          clearTimeout(timer)
          resolve()
        },
        { once: true },
      )
    })

  /**
   * 主循环：首次 + 重试
   */
  const run = async (): Promise<void> => {
    try {
      await fetchOnce()
    } catch (err: any) {
      // 用户主动 abort：不重连
      if (err?.name === 'AbortError') return

      // 正常完成（end event）但 reader 抛错（连接关）也可能到达这里
      if (completed) return

      // Phase 2：连接级 429 / 5xx —— 按退避重连（不要求 streamId，因为尚未开始流式）
      if (err?.name === 'UpstreamRateLimit' || err?.name === 'UpstreamServerError') {
        if (attempt >= maxRetries) {
          onError?.(err?.message || '服务暂时不可用，请稍后再试')
          return
        }
        const delayMs =
          err?.retryAfterMs ?? retryDelays?.[attempt] ?? getBackoffMs(attempt + 1)
        attempt++
        onResume?.(attempt, maxRetries)
        await waitWithAbort(delayMs)
        if (controller.signal.aborted) return
        await run()
        return
      }

      // 其他 4xx（如 401）：不可重试，直接报错
      if (err?.name === 'UpstreamError') {
        onError?.(err?.message || '请求失败')
        return
      }

      // 网络中断：需要 streamId 才能续传
      if (attempt >= maxRetries) {
        onError?.(err?.message || '网络中断，已达最大重试次数')
        return
      }

      // 没拿到 X-Stream-Id：无法续传，直接报错
      if (!streamId) {
        onError?.(err?.message || '网络中断，且服务端未下发 streamId，无法续传')
        return
      }

      // 触发重试
      const delayMs = retryDelays?.[attempt] ?? getBackoffMs(attempt + 1)
      attempt++
      onResume?.(attempt, maxRetries)
      await waitWithAbort(delayMs)
      if (controller.signal.aborted) return

      // 递归：重试
      await run()
    }
  }

  // 异步跑主循环（不 await，不阻塞 controller 返回）
  run().catch((err) => {
    onError?.(err?.message || '未知错误')
  })

  return controller
}

export default request
