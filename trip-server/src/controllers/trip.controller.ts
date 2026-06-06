import { Request, Response } from 'express'
import tripService from '../services/tripService'
import { createStreamResponse } from '../utils/stream'

export const recommend = async (req: Request, res: Response) => {
  const { city, budget, days } = req.body as { city: string; budget: number; days: number }
  if (!city || !budget || !days) {
    return res.status(400).json({
      code: 400,
      error: '参数错误',
    })
  }
  try {
    const result = await tripService.recommend(city, budget, days)
    return res.json(result)
  } catch (error) {
    return res.status(500).json({
      code: 500,
      error: '推荐失败',
    })
  }
}

export const chat = async (req: Request, res: Response) => {
  const { message } = req.body as { message: string }
  if (!message) {
    return res.status(400).json({
      code: 400,
      error: '参数错误',
    })
  }
  const stream = createStreamResponse(res)
  const result = await tripService.chat(message, (chunk: string) => {
    stream.send({ type: 'chunk', content: chunk })
  })
  stream.send({ type: 'complete', data: result })
  stream.end()
}
