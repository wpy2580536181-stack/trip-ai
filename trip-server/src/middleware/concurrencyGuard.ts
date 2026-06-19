import { Request, Response, NextFunction } from 'express'
import { ConcurrencyGuard } from '../services/llmGuard/semaphore'

const LLM_GLOBAL_CONCURRENCY = Number(process.env.LLM_GLOBAL_CONCURRENCY) || 10
const LLM_USER_CONCURRENCY = Number(process.env.LLM_USER_CONCURRENCY) || 1

const guard = new ConcurrencyGuard(LLM_GLOBAL_CONCURRENCY, LLM_USER_CONCURRENCY)

export function concurrencyGuard(req: Request, res: Response, next: NextFunction): void {
  const userId = (req as any).user?.userId ?? null
  const { success, release } = guard.tryAcquire(userId)

  if (!success) {
    res.status(429).json({ code: 429, error: '系统繁忙，请稍后再试' })
    return
  }

  let released = false
  const doRelease = () => {
    if (released) return
    released = true
    release()
  }

  res.on('finish', doRelease)
  res.on('close', doRelease)
  next()
}

export function getConcurrencyStats(): { globalAvailable: number; activeUsers: number } {
  return {
    globalAvailable: (guard as any).global.available,
    activeUsers: (guard as any).perUser.size,
  }
}
