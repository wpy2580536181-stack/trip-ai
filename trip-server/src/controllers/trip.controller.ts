import { Request, Response } from 'express'
import tripService from '../services/tripService'
import { createStreamResponse } from '../utils/stream'

export const recommend = async (req: Request, res: Response) => {
  const { city, budget, days } = req.body as { city: string; budget: number; days: number }
  if (!city || !budget || !days) {
    return res.status(400).json({ code: 400, error: '参数错误' })
  }
  try {
    const result = await tripService.recommend(city, budget, days)
    return res.json(result)
  } catch (error) {
    return res.status(500).json({ code: 500, error: '推荐失败' })
  }
}

export const chat = async (req: Request, res: Response) => {
  const { message, conversationId } = req.body as { message: string; conversationId?: number }
  if (!message) {
    return res.status(400).json({ code: 400, error: '参数错误' })
  }
  if (!req.user) {
    return res.status(401).json({ code: 401, error: '未登录' })
  }

  const stream = createStreamResponse(res)
  const isClientConnected = () => !res.writableEnded && !res.destroyed

  req.on('close', () => {
    if (!isClientConnected()) {
      console.log('[TripController] 客户端断开，标记流结束')
    }
  })

  try {
    const { conversationId: newConvId } = await tripService.chatStream({
      userId: req.user.userId,
      message,
      conversationId,
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
    const errMsg = error instanceof Error ? error.message : '未知错误'
    if (isClientConnected()) {
      stream.error(errMsg)
    }
  }
}
