/**
 * ResumableStream 单元测试
 *
 * 测试对象：utils/stream.ts 的 ResumableStream 包装层
 * 行为契约：
 *  1. createResumableStream 无 streamId → 创建 Redis stream（mock），返回 streamId
 *  2. send(payload) → 同时写 SSE 响应 + 写 Redis（pipe）
 *  3. end() → 写 SSE end + markComplete
 *  4. getStreamId() 返回 streamId（用于 X-Stream-Id 响应头）
 *  5. Redis 不可用时降级：正常 SSE，不写 Redis，不抛错
 *  6. SSE 写入失败时 onWriteError 回调被调
 *
 * 续传路径（resumeStream）测试：
 *  - 重发所有 events from lastSeq
 *  - IDOR 防护：userId 不匹配抛 ForbiddenError
 *  - stream 不存在抛 NotFoundError
 *  - status=completed 仍可重发历史 events
 *  - lastSeq > totalSeq 抛 BadRequestError
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock streamStore
const mockCreateStream = vi.fn()
const mockAppendEvent = vi.fn()
const mockMarkComplete = vi.fn()
const mockGetStreamState = vi.fn()
const mockGetEventsSince = vi.fn()

vi.mock('../../services/streamStore', () => ({
  createStream: (...args: unknown[]) => mockCreateStream(...args),
  appendEvent: (...args: unknown[]) => mockAppendEvent(...args),
  markComplete: (...args: unknown[]) => mockMarkComplete(...args),
  getStreamState: (...args: unknown[]) => mockGetStreamState(...args),
  getEventsSince: (...args: unknown[]) => mockGetEventsSince(...args),
}))

// Mock redis config（控制 isRedisAvailable）
const mockIsRedisAvailable = vi.fn()
vi.mock('../../config/redis', () => ({
  isRedisAvailable: () => mockIsRedisAvailable(),
}))

import {
  createResumableStream,
  resumeStream,
  StreamNotFoundError,
  StreamForbiddenError,
  StreamBadRequestError,
} from '../stream'

// 简单的 mock Response —— 捕获 setHeader / write
function makeMockRes() {
  const headers: Record<string, string> = {}
  const writes: string[] = []
  let ended = false
  const res = {
    setHeader: vi.fn((name: string, value: string) => {
      headers[name] = value
    }),
    flushHeaders: vi.fn(),
    write: vi.fn((data: string) => {
      writes.push(data)
      return true
    }),
    end: vi.fn(() => {
      ended = true
    }),
    writableEnded: false,
    destroyed: false,
    on: vi.fn(),
    headers,
    writes,
    isEnded: () => ended,
  } as any
  return res
}

beforeEach(() => {
  vi.clearAllMocks()
  mockIsRedisAvailable.mockReturnValue(true)
  mockCreateStream.mockResolvedValue({ streamId: 'stream:new-id', seq: 0 })
  mockAppendEvent.mockImplementation(async (_id: string) => ({ seq: Math.floor(Math.random() * 1000) + 1 }))
  mockMarkComplete.mockResolvedValue(undefined)
})

describe('createResumableStream', () => {
  it('无 streamId → 创建新 Redis stream 并返回 streamId', async () => {
    const res = makeMockRes()
    const rs = await createResumableStream({
      res,
      userId: 'u1',
      conversationId: 'c1',
    })

    expect(mockCreateStream).toHaveBeenCalledWith('u1', 'c1')
    expect(rs.getStreamId()).toBe('stream:new-id')
  })

  it('设置 SSE 响应头', async () => {
    const res = makeMockRes()
    await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    expect(res.setHeader).toHaveBeenCalledWith('Content-Type', 'text/event-stream')
    expect(res.setHeader).toHaveBeenCalledWith('Cache-Control', 'no-cache')
    expect(res.setHeader).toHaveBeenCalledWith('Connection', 'keep-alive')
  })

  it('设置 X-Stream-Id 响应头（用于客户端断网续传）', async () => {
    const res = makeMockRes()
    const rs = await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    expect(res.setHeader).toHaveBeenCalledWith('X-Stream-Id', 'stream:new-id')
  })

  it('send → 写 SSE 数据 + 写 Redis event', async () => {
    const res = makeMockRes()
    const rs = await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    rs.send({ type: 'chunk', content: '你好' })

    // 等待 microtask（appendEvent 是 async）
    await new Promise((r) => setTimeout(r, 0))

    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('"content":"你好"'))
    expect(mockAppendEvent).toHaveBeenCalledWith('stream:new-id', {
      type: 'chunk',
      data: { type: 'chunk', content: '你好' },
    })
  })

  it('send → SSE 写 id: 字段（客户端用作 Last-Event-ID）', async () => {
    const res = makeMockRes()
    const rs = await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    rs.send({ type: 'chunk', content: 'A' })
    rs.send({ type: 'chunk', content: 'B' })
    rs.send({ type: 'chunk', content: 'C' })

    expect(res.write).toHaveBeenNthCalledWith(1, expect.stringContaining('id: 1\n'))
    expect(res.write).toHaveBeenNthCalledWith(2, expect.stringContaining('id: 2\n'))
    expect(res.write).toHaveBeenNthCalledWith(3, expect.stringContaining('id: 3\n'))
  })

  it('end → 写 SSE end event + markComplete', async () => {
    const res = makeMockRes()
    const rs = await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    rs.end()

    await new Promise((r) => setTimeout(r, 0))

    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('event: end'))
    expect(mockMarkComplete).toHaveBeenCalledWith('stream:new-id')
  })

  it('Redis 不可用时降级：正常 SSE，不写 Redis，不抛错', async () => {
    mockIsRedisAvailable.mockReturnValue(false)
    const res = makeMockRes()
    const rs = await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    // 不应调 createStream
    expect(mockCreateStream).not.toHaveBeenCalled()
    // getStreamId 返回 null（无法续传）
    expect(rs.getStreamId()).toBeNull()

    // send 仍能写 SSE
    rs.send({ type: 'chunk', content: 'hi' })
    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('"content":"hi"'))

    await new Promise((r) => setTimeout(r, 0))
    // 不应写 Redis
    expect(mockAppendEvent).not.toHaveBeenCalled()

    // end 也不应 markComplete
    rs.end()
    await new Promise((r) => setTimeout(r, 0))
    expect(mockMarkComplete).not.toHaveBeenCalled()
  })

  it('SSE 写入失败时调 onWriteError 回调', async () => {
    const res = makeMockRes()
    res.write = vi.fn(() => {
      throw new Error('socket closed')
    })
    const onWriteError = vi.fn()
    const rs = await createResumableStream({
      res,
      userId: 'u1',
      conversationId: 'c1',
      onWriteError,
    })

    rs.send({ type: 'chunk', content: 'x' })
    expect(onWriteError).toHaveBeenCalled()
  })

  it('setHeader 完成后立即 flushHeaders（让 client 立即拿到 X-Stream-Id）', async () => {
    const res = makeMockRes()
    await createResumableStream({ res, userId: 'u1', conversationId: 'c1' })

    // flushHeaders 必须在第一次 write 之前调用
    // 关键：客户端断网重连场景依赖此——abort 前能拿到 streamId
    expect(res.flushHeaders).toHaveBeenCalledTimes(1)
  })
})

describe('resumeStream', () => {
  it('重发 lastSeq 之后的所有 events', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockResolvedValue({
      streamId: 'stream:abc',
      userId: 'u1',
      conversationId: 'c1',
      status: 'active',
      createdAt: 0,
      lastEventAt: 0,
      totalSeq: 3,
    })
    // ev.data 是 StreamPayload 形式
    mockGetEventsSince.mockResolvedValue([
      { seq: 2, type: 'chunk', data: { type: 'chunk', content: '世' }, createdAt: 0 },
      { seq: 3, type: 'chunk', data: { type: 'chunk', content: '界' }, createdAt: 0 },
    ])

    await resumeStream({ res, streamId: 'stream:abc', lastSeq: 1, userId: 'u1' })

    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('"content":"世"'))
    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('"content":"界"'))
    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('event: end'))
  })

  it('设置 X-Stream-Id 响应头', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockResolvedValue({
      streamId: 'stream:abc',
      userId: 'u1',
      conversationId: 'c1',
      status: 'active',
      createdAt: 0,
      lastEventAt: 0,
      totalSeq: 0,
    })
    mockGetEventsSince.mockResolvedValue([])

    await resumeStream({ res, streamId: 'stream:abc', lastSeq: 0, userId: 'u1' })

    expect(res.setHeader).toHaveBeenCalledWith('X-Stream-Id', 'stream:abc')
  })

  it('IDOR 防护：userId 不匹配抛 StreamForbiddenError', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockResolvedValue({
      streamId: 'stream:abc',
      userId: 'user-OWNER', // 真正的 owner
      conversationId: 'c1',
      status: 'active',
      createdAt: 0,
      lastEventAt: 0,
      totalSeq: 0,
    })

    await expect(
      resumeStream({ res, streamId: 'stream:abc', lastSeq: 0, userId: 'user-ATTACKER' })
    ).rejects.toBeInstanceOf(StreamForbiddenError)
  })

  it('stream 不存在抛 StreamNotFoundError', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockRejectedValue(new Error('Stream not found: stream:xxx'))

    await expect(
      resumeStream({ res, streamId: 'stream:xxx', lastSeq: 0, userId: 'u1' })
    ).rejects.toBeInstanceOf(StreamNotFoundError)
  })

  it('lastSeq 超过 totalSeq 抛 StreamBadRequestError', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockResolvedValue({
      streamId: 'stream:abc',
      userId: 'u1',
      conversationId: 'c1',
      status: 'active',
      createdAt: 0,
      lastEventAt: 0,
      totalSeq: 3,
    })
    mockGetEventsSince.mockRejectedValue(new Error('exceed totalSeq'))

    await expect(
      resumeStream({ res, streamId: 'stream:abc', lastSeq: 999, userId: 'u1' })
    ).rejects.toBeInstanceOf(StreamBadRequestError)
  })

  it('status=completed 仍可重发历史 events', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockResolvedValue({
      streamId: 'stream:abc',
      userId: 'u1',
      conversationId: 'c1',
      status: 'completed',
      createdAt: 0,
      lastEventAt: 0,
      totalSeq: 1,
    })
    // ev.data 是 StreamPayload 形式（appendEvent 存的 data 就是 payload）
    mockGetEventsSince.mockResolvedValue([
      { seq: 1, type: 'complete', data: { type: 'complete', data: { done: true } }, createdAt: 0 },
    ])

    await resumeStream({ res, streamId: 'stream:abc', lastSeq: 0, userId: 'u1' })

    // 应重发历史 event + end
    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('"type":"complete"'))
    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('event: end'))
  })

  it('无 events 可发（已全收到）→ 立即 end', async () => {
    const res = makeMockRes()
    mockGetStreamState.mockResolvedValue({
      streamId: 'stream:abc',
      userId: 'u1',
      conversationId: 'c1',
      status: 'completed',
      createdAt: 0,
      lastEventAt: 0,
      totalSeq: 5,
    })
    mockGetEventsSince.mockResolvedValue([])

    await resumeStream({ res, streamId: 'stream:abc', lastSeq: 5, userId: 'u1' })

    expect(res.write).toHaveBeenCalledWith(expect.stringContaining('event: end'))
  })
})
