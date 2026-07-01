/**
 * Redis 缓存（替代 TTLCache，用于跨 Worker 共享）
 *
 * 实现 CacheAdapter 接口，与 TTLCache 互换。
 * Redis 不可用时降级：get/set 返回 miss，set 静默失败。
 */

import redis, { isRedisAvailable } from '../../config/redis'
import { agentLog as log } from '../../utils/logger'
import type { CacheAdapter } from './cache'

export class RedisTTLCache<V = unknown> implements CacheAdapter<V> {
  private prefix: string

  constructor(opts?: { prefix?: string }) {
    this.prefix = opts?.prefix ?? 'cache'
  }

  private makeKey(key: string): string {
    return `${this.prefix}:${key}`
  }

  async get(key: string): Promise<V | undefined> {
    if (!isRedisAvailable()) return undefined
    try {
      const raw = await redis.get(this.makeKey(key))
      if (raw === null) return undefined
      return JSON.parse(raw) as V
    } catch (e) {
      log.warn({ err: e, key }, 'Redis get 失败，降级')
      return undefined
    }
  }

  async set(key: string, value: V, ttlMs?: number): Promise<void> {
    if (!isRedisAvailable()) return
    try {
      const str = JSON.stringify(value)
      if (ttlMs !== undefined) {
        await redis.set(this.makeKey(key), str, 'PX', ttlMs)
      } else {
        await redis.set(this.makeKey(key), str)
      }
    } catch (e) {
      log.warn({ err: e, key }, 'Redis set 失败')
    }
  }

  async values(): Promise<V[]> {
    if (!isRedisAvailable()) return []
    try {
      const keys = await redis.keys(`${this.prefix}:*`)
      if (keys.length === 0) return []
      const data = await redis.mget(...keys)
      return data
        .filter((d): d is string => d !== null)
        .map(d => JSON.parse(d) as V)
    } catch (e) {
      log.warn({ err: e }, 'Redis values 失败')
      return []
    }
  }
}
