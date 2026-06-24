/**
 * Redis 客户端
 *
 * 用途：
 * 1. 断点续传流式 Agent — 存 SSE events + stream 元数据
 * 2. 未来扩展：限流、缓存、临时状态
 *
 * 配置（环境变量）：
 *   REDIS_HOST     默认 127.0.0.1
 *   REDIS_PORT     默认 6379
 *   REDIS_PASSWORD 默认无
 *   REDIS_DB       默认 0
 *
 * 失败策略：连接失败不阻塞服务启动（降级为无缓存模式）
 */

import Redis from 'ioredis'
import { redisLog as log } from '../utils/logger'

const host = process.env.REDIS_HOST || '127.0.0.1'
const port = Number(process.env.REDIS_PORT) || 6379
const password = process.env.REDIS_PASSWORD || undefined
const db = Number(process.env.REDIS_DB) || 0

const redis = new Redis({
  host,
  port,
  password,
  db,
  // 指数退避重连：50ms, 100ms, 200ms, ... 上限 2s
  retryStrategy: (times) => Math.min(times * 50, 2000),
  // 启动时最多重试 3 次，失败后降级（不抛错）
  maxRetriesPerRequest: 3,
})

let connected = false

redis.on('connect', () => {
  connected = true
  log.info({ host, port, db }, 'Redis 连接成功')
})

redis.on('error', (err) => {
  // 连不上时降级：业务侧应判断 isRedisAvailable()
  if (connected) {
    log.warn({ err: err.message }, 'Redis 连接断开，将重连')
  }
  connected = false
})

redis.on('close', () => {
  if (connected) {
    log.warn('Redis 连接关闭')
  }
  connected = false
})

redis.on('reconnecting', (delay: number) => {
  log.info({ delay }, 'Redis 重连中')
})

/**
 * 检查 Redis 是否可用
 * 不可用时调用方应降级（不抛错）
 */
export function isRedisAvailable(): boolean {
  return connected && redis.status === 'ready'
}

export default redis
