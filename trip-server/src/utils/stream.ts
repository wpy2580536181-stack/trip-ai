import { Response } from 'express'
import {
  createStream,
  appendEvent,
  markComplete,
  getStreamState,
  getEventsSince,
  type StreamEvent,
} from '../services/streamStore'
import { isRedisAvailable } from '../config/redis'
import { streamLog as log } from './logger'

/**
 * 错误类型（让 controller 用 instanceof 区分响应码）
 */
export class StreamNotFoundError extends Error {
  constructor(streamId: string) {
    super(`Stream not found: ${streamId}`)
    this.name = 'StreamNotFoundError'
  }
}

export class StreamForbiddenError extends Error {
  constructor() {
    super('Forbidden: stream belongs to another user')
    this.name = 'StreamForbiddenError'
  }
}

export class StreamBadRequestError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'StreamBadRequestError'
  }
}

export interface StreamPayload {
  type: 'chunk' | 'complete' | 'tool_start' | 'tool_end' | 'error' | 'heartbeat'
  name?: string
  content?: string
  data?: unknown
}

export interface ResumableStreamOptions {
  res: Response
  userId: string | number
  conversationId: string | number
  onWriteError?: () => void
}

export interface ResumableStreamHandle {
  send: (data: StreamPayload) => void
  end: () => void
  error: (message: string) => void
  getStreamId: () => string | null
  isResumable: () => boolean
}

/**
 * 创建可续传的 SSE 流
 *
 * 模式：
 * 1. Redis 可用 → 创建 Redis stream + 写 SSE 边写 Redis（双写）
 * 2. Redis 不可用 → 降级为纯 SSE（不可续传，但不报错）
 *
 * 写顺序：先 SSE 再 Redis（SSE 失败时 onWriteError 回调被调，业务可中止 Agent）
 * 写 Redis 是 fire-and-forget，不阻塞 SSE 流
 */
export async function createResumableStream(
  opts: ResumableStreamOptions
): Promise<ResumableStreamHandle> {
  const { res, userId, conversationId, onWriteError } = opts

  // 设置 SSE 响应头
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')
  // 关闭 nginx buffering（启用流式）
  res.setHeader('X-Accel-Buffering', 'no')

  let streamId: string | null = null
  const resumable = isRedisAvailable()

  if (resumable) {
    try {
      const result = await createStream(String(userId), String(conversationId))
      streamId = result.streamId
      res.setHeader('X-Stream-Id', streamId)
    } catch (err) {
      log.warn({ err: (err as Error).message }, '创建 Redis stream 失败，降级为不可续传')
    }
  } else {
    log.debug('Redis 不可用，跳过 stream 存储')
  }

  const writeSSE = (data: string): boolean => {
    try {
      return res.write(data)
    } catch (err) {
      log.error({ err: (err as Error).message }, 'SSE 写入失败')
      onWriteError?.()
      return false
    }
  }

  return {
    send: (data: StreamPayload) => {
      // 写 SSE（同步）
      const sseOk = writeSSE(`data: ${JSON.stringify(data)}\n\n`)
      if (!sseOk) return

      // 写 Redis（fire-and-forget，不阻塞流）
      if (streamId) {
        appendEvent(streamId, { type: data.type, data })
          .catch((err) => {
            log.warn({ err: (err as Error).message, streamId }, 'Redis 写 event 失败')
          })
      }
    },
    end: () => {
      try {
        writeSSE('event: end\ndata: {"done":true}\n\n')
        res.end()
      } catch (err) {
        log.error({ err: (err as Error).message }, 'SSE 结束错误')
      }
      // markComplete fire-and-forget
      if (streamId) {
        markComplete(streamId).catch((err) => {
          log.warn({ err: (err as Error).message, streamId }, 'markComplete 失败')
        })
      }
    },
    error: (message: string) => {
      try {
        writeSSE(`event: error\ndata: ${JSON.stringify({ type: 'error', error: message })}\n\n`)
        res.end()
      } catch (err) {
        log.error({ err: (err as Error).message, message }, 'SSE 错误响应失败')
      }
    },
    getStreamId: () => streamId,
    isResumable: () => streamId !== null,
  }
}

export interface ResumeStreamOptions {
  res: Response
  streamId: string
  lastSeq: number
  userId: string | number
}

/**
 * 续传 stream：重发 lastSeq 之后的所有 events
 *
 * 错误类型（controller 用 instanceof 区分响应码）：
 *  - StreamNotFoundError  → 400
 *  - StreamForbiddenError → 403（IDOR 防护）
 *  - StreamBadRequestError → 400（lastSeq 超界）
 *
 * 行为：
 *  - status=active 或 completed 都允许重发
 *  - 重发完所有 events 后 end
 *  - 不做实时续传（保持长连接等新 events）—— Day 5-6 实现
 */
export async function resumeStream(opts: ResumeStreamOptions): Promise<void> {
  const { res, streamId, lastSeq, userId } = opts

  let state
  try {
    state = await getStreamState(streamId)
  } catch (err) {
    // streamStore 抛 "Stream not found" → 包装为 NotFoundError
    if ((err as Error).message.includes('not found')) {
      throw new StreamNotFoundError(streamId)
    }
    throw err
  }

  // IDOR 防护：stream owner 必须匹配当前 user
  if (String(state.userId) !== String(userId)) {
    log.warn(
      { streamId, owner: state.userId, requester: userId },
      'IDOR: 用户尝试访问他人 stream'
    )
    throw new StreamForbiddenError()
  }

  // 设置响应头
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('X-Accel-Buffering', 'no')
  res.setHeader('X-Stream-Id', streamId)

  // 读 events
  let events: StreamEvent[]
  try {
    events = await getEventsSince(streamId, lastSeq)
  } catch (err) {
    // "exceed totalSeq" → BadRequestError
    if ((err as Error).message.includes('exceed')) {
      throw new StreamBadRequestError((err as Error).message)
    }
    throw err
  }

  // 重发 events
  for (const ev of events) {
    // ev.data 是 StreamPayload 形式
    const payload = ev.data as StreamPayload
    res.write(`data: ${JSON.stringify(payload)}\n\n`)
  }

  // 写 end
  res.write('event: end\ndata: {"done":true}\n\n')
  res.end()

  log.info(
    { streamId, lastSeq, count: events.length, status: state.status },
    '续传完成'
  )
}
