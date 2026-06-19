const DEFAULT_MAX_SIZE = 100
const DEFAULT_TTL_MS = 3_600_000

interface CacheEntry<V> {
  value: V
  expiresAt: number
}

export class TTLCache<V = unknown> {
  private cache = new Map<string, CacheEntry<V>>()
  private maxSize: number
  private defaultTtlMs: number
  private cleanupTimer: ReturnType<typeof setInterval>

  constructor(opts?: { maxSize?: number; defaultTtlMs?: number }) {
    this.maxSize = opts?.maxSize ?? DEFAULT_MAX_SIZE
    this.defaultTtlMs = opts?.defaultTtlMs ?? DEFAULT_TTL_MS
    this.cleanupTimer = setInterval(() => this.cleanup(), 60_000)
    if (this.cleanupTimer.unref) this.cleanupTimer.unref()
  }

  get(key: string): V | undefined {
    const entry = this.cache.get(key)
    if (!entry) return undefined
    if (Date.now() >= entry.expiresAt) {
      this.cache.delete(key)
      return undefined
    }
    return entry.value
  }

  set(key: string, value: V, ttlMs?: number): void {
    if (this.cache.size >= this.maxSize && !this.cache.has(key)) {
      const oldest = this.cache.keys().next().value
      if (oldest !== undefined) this.cache.delete(oldest)
    }
    this.cache.set(key, {
      value,
      expiresAt: Date.now() + (ttlMs ?? this.defaultTtlMs),
    })
  }

  async getOrCompute(key: string, compute: () => Promise<V>, ttlMs?: number): Promise<V> {
    const existing = this.get(key)
    if (existing !== undefined) return existing
    const value = await compute()
    this.set(key, value, ttlMs)
    return value
  }

  invalidate(key: string): void {
    this.cache.delete(key)
  }

  clear(): void {
    this.cache.clear()
  }

  shutdown(): void {
    clearInterval(this.cleanupTimer)
    this.cache.clear()
  }

  private cleanup(): void {
    const now = Date.now()
    for (const [key, entry] of this.cache) {
      if (now >= entry.expiresAt) this.cache.delete(key)
    }
  }
}

export const recommendCache = new TTLCache<object>({ maxSize: 200, defaultTtlMs: 3_600_000 })
