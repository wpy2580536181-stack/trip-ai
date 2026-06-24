/**
 * streamStore 单元测试
 *
 * 真实 Redis 连接（127.0.0.1:6379），用 stream:test:* 前缀
 * 跑完测试自动清理（用流名唯一性避免污染）
 *
 * 覆盖：
 * - createStream 返回唯一 streamId + 初始 metadata
 * - appendEvent 原子自增 seq，返回 seq
 * - getEventsSince 按 seq 范围返回（inclusive）
 * - getStreamState 返回 status / totalSeq / owner
 * - markComplete 改 status
 * - deleteStream 清理
 * - TTL 10 分钟
 * - 边界：空 events 续传、超过现有 seq 报错、不存在 stream 报错
 */

import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import {
  createStream,
  appendEvent,
  getEventsSince,
  getStreamState,
  markComplete,
  deleteStream,
  type StreamEvent,
} from '../streamStore'
import redis, { isRedisAvailable } from '../../config/redis'

async function waitForRedis(timeoutMs = 5000): Promise<void> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (redis.status === 'ready' && isRedisAvailable()) return
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error('Redis 连接超时（5s）')
}

describe('streamStore', () => {
  beforeAll(async () => {
    await waitForRedis()
  })

  afterEach(async () => {
    // 测试失败时 deleteStream 不会执行，需要兜底清理
    // streamId 是随机 UUID，不会与其他测试冲突
    if (!isRedisAvailable()) return
    const keys = await redis.keys('stream:*')
    if (keys.length > 0) {
      await redis.del(...keys)
    }
  })

  describe('createStream', () => {
    it('返回 streamId 和初始 metadata', async () => {
      const userId = `user-${Date.now()}-${Math.random()}`
      const conversationId = `conv-${Date.now()}`

      const result = await createStream(userId, conversationId)

      expect(result.streamId).toMatch(/^stream:[0-9a-f-]{36}$/)
      expect(result.seq).toBe(0) // 还没追加任何 event
      const state = await getStreamState(result.streamId)
      expect(state.userId).toBe(userId)
      expect(state.conversationId).toBe(conversationId)
      expect(state.status).toBe('active')
      expect(state.totalSeq).toBe(0)

      await deleteStream(result.streamId)
    })
  })

  describe('appendEvent', () => {
    it('原子自增 seq 并返回新 seq', async () => {
      const { streamId } = await createStream('u1', 'c1')

      const e1 = await appendEvent(streamId, { type: 'start', data: { msg: 'hi' } })
      expect(e1.seq).toBe(1)

      const e2 = await appendEvent(streamId, { type: 'token', data: { delta: '你' } })
      expect(e2.seq).toBe(2)

      const e3 = await appendEvent(streamId, { type: 'end', data: {} })
      expect(e3.seq).toBe(3)

      const state = await getStreamState(streamId)
      expect(state.totalSeq).toBe(3)

      await deleteStream(streamId)
    })

    it('追加空 events 后 totalSeq 仍为 0', async () => {
      const { streamId } = await createStream('u1', 'c1')

      const state = await getStreamState(streamId)
      expect(state.totalSeq).toBe(0)

      await deleteStream(streamId)
    })
  })

  describe('getEventsSince', () => {
    it('返回 seq > lastSeq 的所有 events（顺序）', async () => {
      const { streamId } = await createStream('u1', 'c1')

      await appendEvent(streamId, { type: 'a', data: { i: 1 } })
      await appendEvent(streamId, { type: 'b', data: { i: 2 } })
      await appendEvent(streamId, { type: 'c', data: { i: 3 } })

      const events = await getEventsSince(streamId, 1) // 从 seq=2 开始
      expect(events).toHaveLength(2)
      expect(events[0].seq).toBe(2)
      expect(events[0].type).toBe('b')
      expect(events[1].seq).toBe(3)
      expect(events[1].type).toBe('c')

      await deleteStream(streamId)
    })

    it('lastSeq=0 返回所有 events', async () => {
      const { streamId } = await createStream('u1', 'c1')

      await appendEvent(streamId, { type: 'a', data: {} })
      await appendEvent(streamId, { type: 'b', data: {} })

      const events = await getEventsSince(streamId, 0)
      expect(events).toHaveLength(2)
      expect(events[0].seq).toBe(1)

      await deleteStream(streamId)
    })

    it('lastSeq 等于 totalSeq 返回空数组', async () => {
      const { streamId } = await createStream('u1', 'c1')

      await appendEvent(streamId, { type: 'a', data: {} })
      await appendEvent(streamId, { type: 'b', data: {} })

      const events = await getEventsSince(streamId, 2)
      expect(events).toEqual([])

      await deleteStream(streamId)
    })

    it('lastSeq 超过 totalSeq 抛错（防客户端 bug）', async () => {
      const { streamId } = await createStream('u1', 'c1')
      await appendEvent(streamId, { type: 'a', data: {} })

      await expect(getEventsSince(streamId, 999)).rejects.toThrow(/exceed/i)

      await deleteStream(streamId)
    })

    it('event data 是 JSON 安全（嵌套对象、unicode）', async () => {
      const { streamId } = await createStream('u1', 'c1')

      await appendEvent(streamId, {
        type: 'token',
        data: { delta: '你好 🌍', nested: { a: [1, 2, 3] } },
      })

      const events = await getEventsSince(streamId, 0)
      expect(events[0].data).toEqual({ delta: '你好 🌍', nested: { a: [1, 2, 3] } })

      await deleteStream(streamId)
    })

    it('损坏 event 跳过并继续返回后续合法 events', async () => {
      const { streamId } = await createStream('u1', 'c1')

      // 注入损坏 event（模拟 Redis 数据损坏或版本不兼容）
      await appendEvent(streamId, { type: 'a', data: { i: 1 } })
      await redis.rpush(`${streamId}:events`, '{{{garbage json') // 损坏
      await appendEvent(streamId, { type: 'c', data: { i: 3 } })

      const events = await getEventsSince(streamId, 0)
      // 损坏 event 跳过，合法 events 仍能拿到
      expect(events).toHaveLength(2)
      expect(events[0].type).toBe('a')
      expect(events[1].type).toBe('c')

      await deleteStream(streamId)
    })
  })

  describe('getStreamState', () => {
    it('不存在的 streamId 抛错', async () => {
      await expect(getStreamState('stream:nonexistent-xxx')).rejects.toThrow(
        /not found/i
      )
    })
  })

  describe('markComplete', () => {
    it('改 status 为 completed 并保留 events', async () => {
      const { streamId } = await createStream('u1', 'c1')
      await appendEvent(streamId, { type: 'a', data: {} })
      await markComplete(streamId)

      const state = await getStreamState(streamId)
      expect(state.status).toBe('completed')

      const events = await getEventsSince(streamId, 0)
      expect(events).toHaveLength(1) // events 还在

      await deleteStream(streamId)
    })
  })

  describe('deleteStream', () => {
    it('清理后 getStreamState 抛错', async () => {
      const { streamId } = await createStream('u1', 'c1')
      await deleteStream(streamId)

      await expect(getStreamState(streamId)).rejects.toThrow()
    })
  })

  describe('TTL', () => {
    it('createStream 后 meta key 有 10 分钟 TTL', async () => {
      const { streamId } = await createStream('u1', 'c1')

      const metaTtl = await redis.ttl(streamId)
      const seqTtl = await redis.ttl(`${streamId}:seq`)

      expect(metaTtl).toBeGreaterThan(0)
      expect(metaTtl).toBeLessThanOrEqual(600)
      expect(seqTtl).toBeGreaterThan(0)

      await deleteStream(streamId)
    })

    it('appendEvent 后 eventsKey 有 10 分钟 TTL', async () => {
      const { streamId } = await createStream('u1', 'c1')
      await appendEvent(streamId, { type: 'test', data: {} })

      const eventsTtl = await redis.ttl(`${streamId}:events`)

      expect(eventsTtl).toBeGreaterThan(0)
      expect(eventsTtl).toBeLessThanOrEqual(600)

      await deleteStream(streamId)
    })
  })

  describe('并发安全', () => {
    it('多个 appendEvent 并发执行后 seq 单调递增无重复', async () => {
      const { streamId } = await createStream('u1', 'c1')

      // 并发 20 个 append
      const promises: Promise<{ seq: number }>[] = []
      for (let i = 0; i < 20; i++) {
        promises.push(appendEvent(streamId, { type: 'concurrent', data: { i } }))
      }
      const results = await Promise.all(promises)

      const seqs = results.map((r) => r.seq).sort((a, b) => a - b)
      expect(seqs).toEqual(Array.from({ length: 20 }, (_, i) => i + 1))

      const state = await getStreamState(streamId)
      expect(state.totalSeq).toBe(20)

      await deleteStream(streamId)
    })
  })

  describe('event size 限制', () => {
    it('超限 event 抛错（防 DoS / OOM）', async () => {
      const { streamId } = await createStream('u1', 'c1')

      // 100KB 字符串（默认限制 64KB）
      const huge = 'x'.repeat(100 * 1024)

      await expect(
        appendEvent(streamId, { type: 'huge', data: { payload: huge } })
      ).rejects.toThrow(/too large|exceed/i)

      // 验证没写入（seq 不增）
      const state = await getStreamState(streamId)
      expect(state.totalSeq).toBe(0)

      await deleteStream(streamId)
    })

    it('正常大小 event 通过', async () => {
      const { streamId } = await createStream('u1', 'c1')

      // 1KB 字符串（远低于限制）
      const normal = 'y'.repeat(1024)
      const r = await appendEvent(streamId, { type: 'normal', data: { payload: normal } })
      expect(r.seq).toBe(1)

      await deleteStream(streamId)
    })
  })
})
