import CircuitBreaker from 'opossum'
import { logger } from '../../utils/logger'
import { AMAP_CONFIG } from '../../config/amap'
import * as amapMcpClient from './amapMcpClient'

const buckets = new Map<string, { tokens: number; lastRefill: number }>()

function getBucket(key: string): { tokens: number; lastRefill: number } {
  if (!buckets.has(key)) {
    buckets.set(key, { tokens: AMAP_CONFIG.rateLimit.maxPerSecond, lastRefill: Date.now() })
  }
  return buckets.get(key)!
}

function refillBucket(bucket: { tokens: number; lastRefill: number }) {
  const now = Date.now()
  const elapsed = (now - bucket.lastRefill) / 1000
  bucket.tokens = Math.min(AMAP_CONFIG.rateLimit.maxPerSecond, bucket.tokens + elapsed)
  bucket.lastRefill = now
}

function tryConsume(bucket: { tokens: number; lastRefill: number }): boolean {
  refillBucket(bucket)
  if (bucket.tokens >= 1) {
    bucket.tokens -= 1
    return true
  }
  return false
}

const circuitBreaker = new CircuitBreaker(
  async (toolName: string, args: Record<string, unknown>) => {
    return await amapMcpClient.callTool(toolName, args)
  },
  {
    errorThresholdPercentage: AMAP_CONFIG.circuitBreaker.maxFailures * 10,
    resetTimeout: AMAP_CONFIG.circuitBreaker.resetTimeoutMs,
    name: 'amap-mcp',
  }
)

circuitBreaker.on('open', () => logger.warn('[AmapGuards] circuit OPEN'))
circuitBreaker.on('halfOpen', () => logger.info('[AmapGuards] circuit HALF-OPEN'))
circuitBreaker.on('close', () => logger.info('[AmapGuards] circuit CLOSED'))

const cache = new Map<string, { value: string; expiresAt: number }>()
const CACHE_MAX = 500

export interface AmapGuardMetrics {
  calls: number
  successes: number
  failures: number
  cacheHits: number
  circuitOpenCount: number
  avgDurationMs: number
}
const metrics: AmapGuardMetrics = { calls: 0, successes: 0, failures: 0, cacheHits: 0, circuitOpenCount: 0, avgDurationMs: 0 }
let totalDurationMs = 0

export function getMetrics(): AmapGuardMetrics {
  return { ...metrics }
}

export async function call(
  toolName: string,
  args: Record<string, unknown>,
  options?: { cacheTtlMs?: number }
): Promise<string> {
  metrics.calls++
  const cacheKey = `${toolName}:${JSON.stringify(args)}`

  if (!tryConsume(getBucket(toolName))) {
    metrics.failures++
    logger.warn({ toolName }, '[AmapGuards] rate limited')
    throw new Error('AMAP_MCP_RATE_LIMITED')
  }

  if (options?.cacheTtlMs !== 0) {
    const ttl = options?.cacheTtlMs ?? AMAP_CONFIG.cacheTtlMs
    const cached = cache.get(cacheKey)
    if (cached && cached.expiresAt > Date.now()) {
      metrics.cacheHits++
      return cached.value
    }
  }

  const start = Date.now()
  try {
    const result = await circuitBreaker.fire(toolName, args)
    const duration = Date.now() - start
    totalDurationMs += duration
    metrics.avgDurationMs = Math.round(totalDurationMs / metrics.calls)
    metrics.successes++

    if (options?.cacheTtlMs !== 0) {
      const ttl = options?.cacheTtlMs ?? AMAP_CONFIG.cacheTtlMs
      if (cache.size >= CACHE_MAX) {
        const firstKey = cache.keys().next().value
        if (firstKey) cache.delete(firstKey)
      }
      cache.set(cacheKey, { value: result, expiresAt: Date.now() + ttl })
    }

    return result
  } catch (err) {
    metrics.failures++
    if (circuitBreaker.opened) metrics.circuitOpenCount++

    if (err instanceof Error && err.message === 'AMAP_MCP_RATE_LIMITED') throw err
    if (circuitBreaker.opened) {
      throw new Error('AMAP_MCP_CIRCUIT_OPEN')
    }
    throw err
  }
}

export function resetCircuit(): void {
  circuitBreaker.close()
}

export function clearCache(): void {
  cache.clear()
}
