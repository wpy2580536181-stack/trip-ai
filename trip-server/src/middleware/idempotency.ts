import { Request, Response, NextFunction } from 'express'

const DEFAULT_TTL_MS = 3_600_000
const CLEANUP_INTERVAL_MS = 60_000

interface CachedResponse {
  statusCode: number
  body: string
  createdAt: number
}

export interface IdempotencyStore {
  get(key: string): Promise<CachedResponse | null>
  set(key: string, entry: CachedResponse): Promise<void>
}

export class MemoryIdempotencyStore implements IdempotencyStore {
  private data = new Map<string, CachedResponse>()

  constructor(private ttlMs: number = DEFAULT_TTL_MS) {
    const interval = setInterval(() => this.cleanup(), CLEANUP_INTERVAL_MS)
    if (interval.unref) interval.unref()
  }

  async get(key: string): Promise<CachedResponse | null> {
    const entry = this.data.get(key)
    if (!entry) return null
    if (Date.now() - entry.createdAt >= this.ttlMs) {
      this.data.delete(key)
      return null
    }
    return entry
  }

  async set(key: string, entry: CachedResponse): Promise<void> {
    this.data.set(key, entry)
  }

  private cleanup(): void {
    const now = Date.now()
    for (const [key, entry] of this.data) {
      if (now - entry.createdAt >= this.ttlMs) this.data.delete(key)
    }
  }
}

export interface IdempotencyConfig {
  ttlMs?: number
  headerName?: string
  store?: IdempotencyStore
}

export function createIdempotencyMiddleware(config?: IdempotencyConfig) {
  const ttlMs = config?.ttlMs ?? DEFAULT_TTL_MS
  const headerName = (config?.headerName ?? 'Idempotency-Key').toLowerCase()
  const store = config?.store ?? new MemoryIdempotencyStore(ttlMs)

  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    if (req.method !== 'POST') return next()

    const rawKey = req.headers[headerName] as string | undefined
    if (!rawKey) return next()

    const userId = (req as any).user?.userId ?? 'anonymous'
    const fullKey = `${userId}:${rawKey}`

    const cached = await store.get(fullKey)
    if (cached) {
      res.status(cached.statusCode).json(JSON.parse(cached.body))
      return
    }

    const originalJson = res.json.bind(res)
    res.json = function (body: any) {
      if (res.statusCode >= 200 && res.statusCode < 300) {
        store.set(fullKey, {
          statusCode: res.statusCode,
          body: JSON.stringify(body),
          createdAt: Date.now(),
        })
      }
      return originalJson(body)
    }

    next()
  }
}
