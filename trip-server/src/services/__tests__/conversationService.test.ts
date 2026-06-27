/**
 * getContextMessages 单元测试
 *
 * 覆盖：
 * - 按时间正序返回所有未 excluded 的消息
 * - 过滤掉 excludedFromContext=true 的消息
 * - 累计 token 正确（CJK ÷ 1.5 + 其他 ÷ 4）
 * - needsCompaction 标志在 totalTokens > maxTokens 时为 true
 * - 边界：空消息、刚好等号、单条消息超限
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockMessageFindMany = vi.fn()

vi.mock('../../config/database', () => ({
  default: {
    message: {
      findMany: (...args: unknown[]) => mockMessageFindMany(...args),
    },
  },
}))

import { getContextMessages } from '../conversationService'

function makeMsg(id: number, content: string, excluded = false) {
  return {
    id,
    conversationId: 1,
    role: 'user',
    content,
    metadata: null,
    excludedFromContext: excluded,
    createdAt: new Date(2026, 0, 1, 0, 0, id),
  }
}

describe('getContextMessages', () => {
  beforeEach(() => {
    mockMessageFindMany.mockReset()
  })

  it('空消息列表：返回空 + 不需要压缩', async () => {
    mockMessageFindMany.mockResolvedValue([])
    const r = await getContextMessages(1, 16000)
    expect(r.messages).toEqual([])
    expect(r.totalTokens).toBe(0)
    expect(r.needsCompaction).toBe(false)
  })

  it('按时间正序返回所有未 excluded 的消息', async () => {
    const msgs = [
      makeMsg(1, '消息1'),
      makeMsg(2, '消息2'),
      makeMsg(3, '消息3'),
    ]
    mockMessageFindMany.mockResolvedValue(msgs)
    const r = await getContextMessages(1, 16000)
    expect(r.messages.map(m => m.id)).toEqual([1, 2, 3])
  })

  it('过滤掉 excludedFromContext=true 的消息', async () => {
    const msgs = [
      makeMsg(1, '已压缩', true),
      makeMsg(2, '保留2'),
      makeMsg(3, '保留3'),
    ]
    mockMessageFindMany.mockResolvedValue([msgs[1], msgs[2]])
    const r = await getContextMessages(1, 16000)
    expect(r.messages.map(m => m.id)).toEqual([2, 3])
  })

  it('调用 prisma 时正确传 where 条件（排除 excluded）', async () => {
    mockMessageFindMany.mockResolvedValue([])
    await getContextMessages(42, 16000)
    expect(mockMessageFindMany).toHaveBeenCalledWith({
      where: { conversationId: 42, excludedFromContext: { not: true } },
      orderBy: { createdAt: 'asc' },
    })
  })

  it('累计 token：CJK 字符按 1.5 字符/token 算', async () => {
    // 30 个中文字符 = 30 / 1.5 = 20 token
    const content = '一二三四五六七八九十'.repeat(3)  // 30 字
    mockMessageFindMany.mockResolvedValue([makeMsg(1, content)])
    const r = await getContextMessages(1, 16000)
    expect(r.totalTokens).toBe(20)
  })

  it('累计 token：英文按 4 字符/token 算', async () => {
    // 40 个英文 = 40 / 4 = 10 token
    const content = 'abcdefghijklmnopqrstuvwxyz0123456789abcd'  // 40 chars
    mockMessageFindMany.mockResolvedValue([makeMsg(1, content)])
    const r = await getContextMessages(1, 16000)
    expect(r.totalTokens).toBe(10)
  })

  it('needsCompaction: 总量 ≤ maxTokens 时为 false', async () => {
    // 60 token
    const content = '中'.repeat(90)  // 90 / 1.5 = 60 token
    mockMessageFindMany.mockResolvedValue([makeMsg(1, content)])
    const r = await getContextMessages(1, 100)
    expect(r.totalTokens).toBe(60)
    expect(r.needsCompaction).toBe(false)
  })

  it('needsCompaction: 总量 > maxTokens 时为 true', async () => {
    const content = '中'.repeat(90)  // 60 token
    mockMessageFindMany.mockResolvedValue([makeMsg(1, content)])
    const r = await getContextMessages(1, 50)
    expect(r.totalTokens).toBe(60)
    expect(r.needsCompaction).toBe(true)
  })

  it('边界：刚好等于 maxTokens 时不压缩（> 不是 >=）', async () => {
    const content = '中'.repeat(150)  // 100 token
    mockMessageFindMany.mockResolvedValue([makeMsg(1, content)])
    const r = await getContextMessages(1, 100)
    expect(r.totalTokens).toBe(100)
    expect(r.needsCompaction).toBe(false)
  })

  it('多消息累计：3 条各 30 token，总 90 token', async () => {
    const content = '中'.repeat(45)  // 30 token each
    mockMessageFindMany.mockResolvedValue([
      makeMsg(1, content),
      makeMsg(2, content),
      makeMsg(3, content),
    ])
    const r = await getContextMessages(1, 100)
    expect(r.totalTokens).toBe(90)
    expect(r.needsCompaction).toBe(false)

    const r2 = await getContextMessages(1, 80)
    expect(r2.needsCompaction).toBe(true)
  })
})
