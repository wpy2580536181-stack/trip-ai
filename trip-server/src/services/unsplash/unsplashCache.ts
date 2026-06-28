const cache = new Map<string, { url: string; expiresAt: number }>()
const MAX_SIZE = 1000

export function getCache(key: string): string | undefined {
  const entry = cache.get(key)
  if (entry && entry.expiresAt > Date.now()) return entry.url
  if (entry) cache.delete(key)
  return undefined
}

export function setCache(key: string, url: string, ttlMs: number): void {
  if (cache.size >= MAX_SIZE) {
    const first = cache.keys().next().value
    if (first) cache.delete(first)
  }
  cache.set(key, { url, expiresAt: Date.now() + ttlMs })
}

export function clearCache(): void { cache.clear() }
export function cacheSize(): number { return cache.size }
