import { Request, Response, NextFunction } from 'express'

const CLEANUP_INTERVAL_MS = 60_000

export interface RateLimitEntry {
  count: number
  resetAt: number
}

export interface RateLimitStore {
  increment(key: string, windowMs: number): Promise<{ count: number; resetAt: number }>
  resetKey(key: string): Promise<void>
}

export class MemoryStore implements RateLimitStore {
  private data = new Map<string, RateLimitEntry>()
  private interval: ReturnType<typeof setInterval>

  constructor() {
    this.interval = setInterval(() => this.cleanup(), CLEANUP_INTERVAL_MS)
    if (this.interval.unref) this.interval.unref()
  }

  async increment(key: string, windowMs: number): Promise<{ count: number; resetAt: number }> {
    const now = Date.now()
    const entry = this.data.get(key)
    if (!entry || now >= entry.resetAt) {
      const resetAt = now + windowMs
      this.data.set(key, { count: 1, resetAt })
      return { count: 1, resetAt }
    }
    entry.count++
    return { count: entry.count, resetAt: entry.resetAt }
  }

  async resetKey(key: string): Promise<void> {
    this.data.delete(key)
  }

  shutdown(): void {
    clearInterval(this.interval)
    this.data.clear()
  }

  private cleanup(): void {
    const now = Date.now()
    for (const [key, entry] of this.data) {
      if (now >= entry.resetAt) this.data.delete(key)
    }
  }
}

export interface LimiterConfig {
  windowMs?: number
  max?: number
  message?: string
  keyGenerator?: (req: Request) => string
  store?: RateLimitStore
}

const defaultKeyGenerator = (req: Request): string => {
  return String((req as any).user?.userId ?? req.ip)
}

export function createLimiter(config: LimiterConfig) {
  const {
    windowMs = 60_000,
    max = 20,
    message = '请求过于频繁，请稍后再试',
    keyGenerator = defaultKeyGenerator,
    store = new MemoryStore(),
  } = config

  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    const key = keyGenerator(req)
    const { count, resetAt } = await store.increment(key, windowMs)
    res.setHeader('X-RateLimit-Limit', String(max))
    res.setHeader('X-RateLimit-Remaining', String(Math.max(0, max - count)))
    res.setHeader('X-RateLimit-Reset', String(Math.ceil(resetAt / 1000)))

    if (count > max) {
      res.status(429).json({ code: 429, error: message })
      return
    }
    next()
  }
}

export function createTokenBudgetGuard(config: {
  maxPerUser?: number
  maxGlobal?: number
  windowMs?: number
  message?: string
}): { middleware: ReturnType<typeof createLimiter>; store: MemoryStore } {
  const store = new MemoryStore()
  return {
    middleware: createLimiter({
      windowMs: config.windowMs ?? 3_600_000,
      max: config.maxPerUser ?? 50_000,
      message: config.message ?? 'Token 额度已用尽，请稍后再试',
      store,
    }),
    store,
  }
}
