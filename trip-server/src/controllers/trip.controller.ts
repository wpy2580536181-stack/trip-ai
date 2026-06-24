import { Request, Response } from 'express'
import tripService from '../services/tripService'
import { optimizeTrip } from '../services/optimizeService'
import {
  createResumableStream,
  resumeStream,
  StreamNotFoundError,
  StreamForbiddenError,
  StreamBadRequestError,
} from '../utils/stream'
import { tripLog as log } from '../utils/logger'

export const recommend = async (req: Request, res: Response) => {
  const { city, budget, days, departureCity } = req.body as {
    city: string
    budget: number
    days: number
    departureCity?: string
  }
  if (!city || !budget || !days) {
    return res.status(400).json({ code: 400, error: '参数错误' })
  }
  const userId = req.user?.userId ?? null
  try {
    const result = await tripService.recommend(city, budget, days, userId, departureCity)
    return res.json(result)
  } catch (error) {
    return res.status(500).json({ code: 500, error: '推荐失败' })
  }
}

export const chat = async (req: Request, res: Response) => {
  const { message, conversationId } = req.body as { message: string; conversationId?: number }
  const streamId = req.header('X-Stream-Id') || undefined
  const lastEventIdHeader = req.header('Last-Event-ID')
  const lastSeq = lastEventIdHeader ? Number(lastEventIdHeader) : 0

  // 续传路径：有 X-Stream-Id + Last-Event-ID → 从 Redis 重发
  if (streamId && lastEventIdHeader) {
    if (!req.user) {
      return res.status(401).json({ code: 401, error: '未登录' })
    }
    if (Number.isNaN(lastSeq) || lastSeq < 0) {
      return res.status(400).json({ code: 400, error: 'Last-Event-ID 必须是非负整数' })
    }

    try {
      await resumeStream({
        res,
        streamId,
        lastSeq,
        userId: String(req.user.userId),
      })
    } catch (err) {
      if (err instanceof StreamNotFoundError) {
        return res.status(404).json({ code: 404, error: 'stream 不存在或已过期' })
      }
      if (err instanceof StreamForbiddenError) {
        return res.status(403).json({ code: 403, error: '无权访问此 stream' })
      }
      if (err instanceof StreamBadRequestError) {
        return res.status(400).json({ code: 400, error: err.message })
      }
      log.error({ err: (err as Error).message, streamId }, '续传失败')
      return res.status(500).json({ code: 500, error: '续传失败' })
    }
    return
  }

  // 正常流式路径
  if (!message) {
    return res.status(400).json({ code: 400, error: '参数错误' })
  }
  if (!req.user) {
    return res.status(401).json({ code: 401, error: '未登录' })
  }

  const abortController = new AbortController()
  const abortAndLog = () => {
    if (!abortController.signal.aborted) {
      abortController.abort()
      log.warn('写入失败，已中止 Agent')
    }
  }
  const stream = await createResumableStream({
    res,
    userId: String(req.user.userId),
    conversationId: conversationId ? String(conversationId) : 'pending',
    onWriteError: abortAndLog,
  })
  const isClientConnected = () => !res.writableEnded && !res.destroyed

  req.on('close', () => {
    if (!abortController.signal.aborted) {
      abortController.abort()
      log.warn('客户端断开，已中止 Agent')
    }
  })

  const heartbeatTimer = setInterval(() => {
    if (!isClientConnected()) {
      abortAndLog()
      clearInterval(heartbeatTimer)
      return
    }
    stream.send({ type: 'heartbeat' })
  }, 5000)

  try {
    const { conversationId: newConvId } = await tripService.chatStream({
      userId: req.user.userId,
      message,
      conversationId,
      signal: abortController.signal,
      callbacks: {
        onChunk: (chunk) => {
          if (isClientConnected()) {
            stream.send({ type: 'chunk', content: chunk })
          }
        },
        onToolStart: (name) => {
          if (isClientConnected()) {
            stream.send({ type: 'tool_start', name })
          }
        },
        onToolEnd: (name) => {
          if (isClientConnected()) {
            stream.send({ type: 'tool_end', name })
          }
        },
        isClientConnected,
      },
    })

    if (isClientConnected()) {
      stream.send({ type: 'complete', data: { conversationId: newConvId } })
      stream.end()
    }
  } catch (error) {
    if (abortController.signal.aborted) {
      log.warn('Agent 已中止，忽略错误')
      return
    }
    const errMsg = error instanceof Error ? error.message : '未知错误'
    if (isClientConnected()) {
      stream.error(errMsg)
    }
  } finally {
    clearInterval(heartbeatTimer)
  }
}

export const optimize = async (req: Request, res: Response) => {
  const { tripId, instruction } = req.body as { tripId: number; instruction?: string }
  if (!tripId) {
    return res.status(400).json({ code: 400, error: '参数错误：缺少 tripId' })
  }
  const userId = req.user?.userId ?? null
  try {
    const result = await optimizeTrip(tripId, instruction ?? '', userId)
    return res.json(result)
  } catch (error) {
    const msg = error instanceof Error ? error.message : '优化失败'
    return res.status(500).json({ code: 500, error: msg })
  }
}
