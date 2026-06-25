/**
 * 告警去重器
 *
 * Redis 5 分钟桶：alert:feedback:low:{timestamp}
 * 同窗口内不重发，避免告警轰炸
 *
 * Redis 不可用时旁路（不阻断告警，但可能重复）
 */

import redis, { isRedisAvailable } from '../../config/redis'
import { alertLog as log } from '../../utils/logger'

const BUCKET_MINUTES = 5
const TTL_SECONDS = BUCKET_MINUTES * 2 * 60  // 10 分钟（覆盖窗口 + 时钟偏移）

class AlertDeduplicator {
  private key(now: Date = new Date()): string {
    const bucketTs = Math.floor(now.getTime() / (BUCKET_MINUTES * 60 * 1000))
    return `alert:feedback:low:${bucketTs}`
  }

  /** 是否应该发送（未被去重） */
  async shouldSend(): Promise<boolean> {
    if (!isRedisAvailable()) {
      log.warn('Redis 不可用，告警去重旁路')
      return true
    }
    try {
      const k = this.key()
      const exists = await redis.exists(k)
      return exists === 0
    } catch (e) {
      log.warn({ err: e }, '去重检查失败，旁路')
      return true
    }
  }

  /** 标记已发送（10 分钟 TTL） */
  async markSent(): Promise<void> {
    if (!isRedisAvailable()) return
    try {
      const k = this.key()
      await redis.set(k, '1', 'EX', TTL_SECONDS)
    } catch (e) {
      log.warn({ err: e }, '标记告警已发送失败')
    }
  }
}

export const alertDeduplicator = new AlertDeduplicator()
