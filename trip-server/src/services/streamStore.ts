/**
 * StreamStore — Redis 存储 SSE 流状态 + events
 *
 * 用途：断点续传流式 Agent
 * 客户端断网后用 Last-Event-ID 头请求续传，服务端
 * 从 Redis 读取缺失的 events 重发。
 *
 * Redis key 设计（streamId 形如 `stream:{uuid}`）：
 *   {streamId}            HASH   { status, userId, conversationId, createdAt, lastEventAt }
 *   {streamId}:events     LIST   JSON 化 events，RPUSH 追加（首个 appendEvent 时创建）
 *   {streamId}:seq        STRING 原子自增 seq 计数器
 *
 * TTL: 10 分钟（SSE 流临时数据，客户端重连后立即续传）
 *
 * 并发安全：用 INCR 原子自增 seq，多客户端同时 append 不会冲突
 *
 * IDOR 防护：getStreamState 返回 ownerId，controller 端应
 * 检查 userId 匹配后才允许续传。
 *
 * 失败策略：Redis 不可用时抛错，调用方（controller）应
 * 降级为非续传模式（直接走正常流式响应，不报错）
 */

import { randomUUID } from 'crypto'
import redis, { isRedisAvailable } from '../config/redis'
import { streamLog as log } from '../utils/logger'

const TTL_SECONDS = 600 // 10 分钟
const MAX_EVENT_SIZE = 64 * 1024 // 64KB，单 event 上限（防 DoS / OOM）

export type StreamStatus = 'active' | 'completed' | 'error'

export interface StreamEvent {
  seq: number
  type: string
  data: unknown
  createdAt: number
}

export interface StreamState {
  streamId: string
  userId: string
  conversationId: string
  status: StreamStatus
  createdAt: number
  lastEventAt: number
  totalSeq: number
}

export interface CreateStreamResult {
  streamId: string
  seq: number
}

/**
 * 内部 key 派生。streamId 已经是完整 Redis key（`stream:{uuid}`），
 * 内部用 eventsKey() / seqKey() 加后缀派生。
 *
 * 设计选择：streamId 包含 namespace，避免重复前缀。
 */
function eventsKey(streamId: string): string {
  return `${streamId}:events`
}

function seqKey(streamId: string): string {
  return `${streamId}:seq`
}

/**
 * 创建新 stream，返回 streamId
 *
 * 客户端应将 streamId 存到本地（localStorage / 内存），
 * 断网重连时用 Last-Event-ID 头传给服务端
 */
export async function createStream(
  userId: string,
  conversationId: string
): Promise<CreateStreamResult> {
  if (!isRedisAvailable()) {
    throw new Error('Redis unavailable, cannot create stream')
  }

  const streamId = `stream:${randomUUID()}`
  const now = Date.now()

  const pipe = redis.pipeline()
  pipe.hset(streamId, {
    userId,
    conversationId,
    status: 'active',
    createdAt: now.toString(),
    lastEventAt: now.toString(),
  })
  // 初始化 seq 计数器为 0
  pipe.set(seqKey(streamId), 0)
  pipe.expire(streamId, TTL_SECONDS)
  pipe.expire(seqKey(streamId), TTL_SECONDS)

  await pipe.exec()

  // eventsKey 暂不存在，等第一个 appendEvent 时创建
  log.debug({ streamId, userId, conversationId }, 'Stream created')

  return { streamId, seq: 0 }
}

/**
 * 追加 event 到 stream，原子自增 seq
 *
 * 返回带 seq 的 event，调用方应将 seq 作为 Last-Event-ID
 * 发给客户端（一般是 SSE 协议的 id: 字段）
 */
export async function appendEvent(
  streamId: string,
  event: { type: string; data: unknown }
): Promise<{ seq: number }> {
  if (!isRedisAvailable()) {
    throw new Error('Redis unavailable, cannot append event')
  }

  // Size check 在 INCR 之前：避免超限 event 跳号
  // （先 INCR 后失败会导致后续 seq 跳号，影响客户端续传）
  const serialized = JSON.stringify({ type: event.type, data: event.data })
  if (serialized.length > MAX_EVENT_SIZE) {
    throw new Error(
      `Event too large: ${serialized.length} bytes (max ${MAX_EVENT_SIZE})`
    )
  }

  // 原子自增 seq
  const seq = await redis.incr(seqKey(streamId))
  const now = Date.now()

  const fullEvent: StreamEvent = {
    seq,
    type: event.type,
    data: event.data,
    createdAt: now,
  }

  const pipe = redis.pipeline()
  pipe.rpush(eventsKey(streamId), JSON.stringify(fullEvent))
  pipe.hset(streamId, { lastEventAt: now.toString() })
  // 每次追加都续期 TTL（流活跃则不过期）
  pipe.expire(streamId, TTL_SECONDS)
  pipe.expire(eventsKey(streamId), TTL_SECONDS)
  pipe.expire(seqKey(streamId), TTL_SECONDS)

  await pipe.exec()

  return { seq }
}

/**
 * 获取 seq > lastSeq 的所有 events
 *
 * 客户端断网重连时传 lastSeq=最后收到的 seq，
 * 服务端从 Redis 读缺失的 events 重发
 *
 * 边界：lastSeq 超过现有 totalSeq 抛错（防客户端 bug）
 */
export async function getEventsSince(
  streamId: string,
  lastSeq: number
): Promise<StreamEvent[]> {
  if (!isRedisAvailable()) {
    throw new Error('Redis unavailable, cannot get events')
  }

  const state = await getStreamState(streamId)

  if (lastSeq > state.totalSeq) {
    throw new Error(
      `Last-Event-ID ${lastSeq} exceeds totalSeq ${state.totalSeq} for stream ${streamId}`
    )
  }

  if (lastSeq >= state.totalSeq) {
    return []
  }

  // LRANGE 索引 0-based
  // seq 从 1 开始 → events[0] = seq 1 → LRANGE 0 = seq 1
  // lastSeq=0 → 要 seq 1..totalSeq → LRANGE 0 -1
  // lastSeq=1 → 要 seq 2..totalSeq → LRANGE 1 -1
  // lastSeq=N → 要 seq N+1..totalSeq → LRANGE N -1
  const startIdx = lastSeq
  const endIdx = -1
  const raw = await redis.lrange(eventsKey(streamId), startIdx, endIdx)

  // 损坏 event 跳过（不致命，log warn 即可）
  // 场景：Redis 数据被手动改、版本不兼容、序列化截断
  const events: StreamEvent[] = []
  for (const s of raw) {
    try {
      events.push(JSON.parse(s) as StreamEvent)
    } catch (err) {
      log.warn(
        { streamId, err: (err as Error).message, raw: s.slice(0, 100) },
        '损坏 event 跳过'
      )
    }
  }
  return events
}

/**
 * 获取 stream 状态
 *
 * 用于：
 * 1. 续传时检查 status（completed 就不续了）
 * 2. IDOR 防护（对比 userId）
 */
export async function getStreamState(streamId: string): Promise<StreamState> {
  if (!isRedisAvailable()) {
    throw new Error('Redis unavailable, cannot get stream state')
  }

  const hash = await redis.hgetall(streamId)

  if (!hash || !hash.userId) {
    throw new Error(`Stream not found: ${streamId}`)
  }

  // seq 单独读
  const seqStr = await redis.get(seqKey(streamId))
  const totalSeq = Number(seqStr) || 0

  return {
    streamId,
    userId: hash.userId,
    conversationId: hash.conversationId,
    status: hash.status as StreamStatus,
    createdAt: Number(hash.createdAt),
    lastEventAt: Number(hash.lastEventAt),
    totalSeq,
  }
}

/**
 * 标记 stream 完成
 *
 * 客户端收到 end event 后调用（或 controller 在流结束后调用）
 * 不删除 events，允许客户端在 TTL 内随时续传
 */
export async function markComplete(streamId: string): Promise<void> {
  if (!isRedisAvailable()) {
    throw new Error('Redis unavailable, cannot mark complete')
  }

  await redis.hset(streamId, { status: 'completed' })
  log.debug({ streamId }, 'Stream marked completed')
}

/**
 * 删除 stream（清理用）
 */
export async function deleteStream(streamId: string): Promise<void> {
  if (!isRedisAvailable()) {
    return // 降级
  }

  const pipe = redis.pipeline()
  pipe.del(streamId)
  pipe.del(eventsKey(streamId))
  pipe.del(seqKey(streamId))
  await pipe.exec()

  log.debug({ streamId }, 'Stream deleted')
}
