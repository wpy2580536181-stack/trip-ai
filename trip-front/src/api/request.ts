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

export function post<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.post(url, params)
}

export function get<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.get(url, { params })
}

export function put<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.put(url, params)
}

export function del<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.delete(url, { params })
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
   * 主循环：首次 + 重试
   */
  const run = async (): Promise<void> => {
    try {
      await fetchOnce()
    } catch (err: any) {
      // 用户主动 abort：不重连
      if (err?.name === 'AbortError') return

      // 正常完成（end event）但 reader 抛错（连接关）也可能到达这里
      // 此时 completed 已是 true，不重连
      if (completed) return

      // 网络中断：尝试重连
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

      // 等退避（同时监听 abort）
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, delayMs)
        controller.signal.addEventListener('abort', () => {
          clearTimeout(timer)
          resolve()
        })
      })

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
