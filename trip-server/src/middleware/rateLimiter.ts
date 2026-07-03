import { Request, Response, NextFunction } from 'express'
import { tokenBudget } from '../services/llmGuard/tokenBudget'
import Redis from 'ioredis'
import { logger } from '../utils/logger'

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

/**
 * Redis-backed store for rate limiting.
 * Uses INCR with EXPIRE for atomic windowed counting.
 */
export class RedisStore implements RateLimitStore {
  private client: Redis

  constructor(client: Redis) {
    this.client = client
  }

  async increment(key: string, windowMs: number): Promise<{ count: number; resetAt: number }> {
    const resetAt = Date.now() + windowMs
    const ttlSeconds = Math.ceil(windowMs / 1000)

    // Use multi() for atomicity
    const multi = this.client.multi()
    multi.incr(key)
    multi.expire(key, ttlSeconds)

    const results = await multi.exec()
    const count = (results?.[0]?.[1] as number) || 1

    return { count, resetAt }
  }

  async resetKey(key: string): Promise<void> {
    await this.client.del(key)
  }
}

/**
 * Create default store based on environment configuration.
 * - RATE_LIMIT_STORE=redis: Use Redis-backed store
 * - Otherwise: Use in-memory store
 */
function createDefaultStore(): RateLimitStore {
  const storeType = process.env.RATE_LIMIT_STORE?.toLowerCase()

  if (storeType === 'redis') {
    const redisClient = new Redis({
      host: process.env.REDIS_HOST || '127.0.0.1',
      port: Number(process.env.REDIS_PORT) || 6379,
      password: process.env.REDIS_PASSWORD || undefined,
      db: Number(process.env.REDIS_DB) || 0,
    })

    logger.info('[RateLimiter] Using Redis store')
    return new RedisStore(redisClient)
  }

  logger.info('[RateLimiter] Using in-memory store')
  return new MemoryStore()
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

/**
 * Create a rate limiter middleware.
 * Supports Redis store via environment variables:
 *   - RATE_LIMIT_STORE=redis (default: memory)
 *   - REDIS_HOST / REDIS_PORT / REDIS_PASSWORD (standard Redis env vars)
 */
export function createLimiter(config: LimiterConfig) {
  const {
    windowMs = 60_000,
    max = 20,
    message = '请求过于频繁，请稍后再试',
    keyGenerator = defaultKeyGenerator,
    store = createDefaultStore(),
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

export function createTokenBudgetGuard(config?: {
  userMessage?: string
  globalMessage?: string
}) {
  const userMsg = config?.userMessage ?? 'Token 额度已用尽，请稍后再试'
  const globalMsg = config?.globalMessage ?? '系统 Token 配额已满，请稍后再试'

  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    const userId = (req as any).user?.userId ?? 'anonymous'
    const userBudget = tokenBudget.checkUserBudget(userId)
    if (!userBudget.allowed) {
      res.status(429).json({ code: 429, error: userMsg })
      return
    }

    const globalBudget = tokenBudget.checkGlobalBudget()
    if (!globalBudget.allowed) {
      res.status(429).json({ code: 429, error: globalMsg })
      return
    }

    next()
  }
}
