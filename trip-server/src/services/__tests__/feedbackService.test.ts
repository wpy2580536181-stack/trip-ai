/**
 * FeedbackService 单元测试
 *
 * mock prisma，只测服务层逻辑：
 * - submit 上送参数正确性
 * - upsert 行为（首次 create vs 二次 update）
 * - getMessageStats 聚合正确
 * - 防滥用：comment 截断 500、tags 限 5
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock prisma
const mockUpsert = vi.fn()
const mockCount = vi.fn()
const mockFindMany = vi.fn()
const mockMessageFindMany = vi.fn()

vi.mock('../../config/database', () => ({
  default: {
    feedback: {
      upsert: (...args: any[]) => mockUpsert(...args),
      count: (...args: any[]) => mockCount(...args),
      findMany: (...args: any[]) => mockFindMany(...args),
    },
    message: {
      findMany: (...args: any[]) => mockMessageFindMany(...args),
    },
  },
}))

import { feedbackService } from '../feedbackService'

describe('FeedbackService.submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('调用 upsert 传正确参数', async () => {
    mockUpsert.mockResolvedValue({ id: 1, rating: 1 })

    await feedbackService.submit({
      userId: 10,
      messageId: 100,
      conversationId: 5,
      rating: 1,
      comment: '很好',
      tags: ['推荐准'],
    })

    expect(mockUpsert).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { userId_messageId: { userId: 10, messageId: 100 } },
        create: expect.objectContaining({
          userId: 10,
          messageId: 100,
          conversationId: 5,
          rating: 1,
          comment: '很好',
          tags: ['推荐准'],
        }),
        update: expect.objectContaining({
          rating: 1,
          comment: '很好',
          tags: ['推荐准'],
        }),
      }),
    )
  })

  it('重复提交走 update（同一 userId+messageId）', async () => {
    mockUpsert.mockResolvedValue({ id: 1, rating: -1 })

    await feedbackService.submit({
      userId: 10,
      messageId: 100,
      conversationId: 5,
      rating: -1,
    })

    // 验证 where 用了 userId_messageId 复合键
    expect(mockUpsert.mock.calls[0][0].where).toEqual({
      userId_messageId: { userId: 10, messageId: 100 },
    })
  })

  it('comment 超过 500 字符被截断', async () => {
    mockUpsert.mockResolvedValue({ id: 1, rating: -1 })

    const longComment = 'x'.repeat(1000)
    await feedbackService.submit({
      userId: 10,
      messageId: 100,
      conversationId: 5,
      rating: -1,
      comment: longComment,
    })

    const passedComment = mockUpsert.mock.calls[0][0].create.comment
    expect(passedComment.length).toBe(500)
  })

  it('tags 超过 5 个被截断到前 5 个', async () => {
    mockUpsert.mockResolvedValue({ id: 1, rating: -1 })

    const manyTags = ['t1', 't2', 't3', 't4', 't5', 't6', 't7']
    await feedbackService.submit({
      userId: 10,
      messageId: 100,
      conversationId: 5,
      rating: -1,
      tags: manyTags,
    })

    const passedTags = mockUpsert.mock.calls[0][0].create.tags
    expect(passedTags).toEqual(['t1', 't2', 't3', 't4', 't5'])
  })

  it('空 tags 数组走 Prisma.JsonNull', async () => {
    mockUpsert.mockResolvedValue({ id: 1, rating: 1 })

    await feedbackService.submit({
      userId: 10,
      messageId: 100,
      conversationId: 5,
      rating: 1,
      tags: [],
    })

    // tags = undefined 或 empty 时会传 Prisma.JsonNull
    const passedTags = mockUpsert.mock.calls[0][0].create.tags
    expect(passedTags).toBeDefined()  // Prisma.JsonNull 不等于 undefined
  })

  it('upsert 抛错时 service 也抛错（不吞）', async () => {
    mockUpsert.mockRejectedValue(new Error('DB error'))

    await expect(
      feedbackService.submit({
        userId: 10,
        messageId: 100,
        conversationId: 5,
        rating: 1,
      }),
    ).rejects.toThrow('DB error')
  })
})

describe('FeedbackService.getMessageStats', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('统计 up/down/total 和 satisfactionRate', async () => {
    mockCount
      .mockResolvedValueOnce(7)  // up
      .mockResolvedValueOnce(3)  // down

    const stats = await feedbackService.getMessageStats(100)

    expect(stats).toEqual({
      up: 7,
      down: 3,
      total: 10,
      satisfactionRate: 0.7,
    })
    expect(mockCount).toHaveBeenCalledTimes(2)
    expect(mockCount).toHaveBeenNthCalledWith(1, { where: { messageId: 100, rating: 1 } })
    expect(mockCount).toHaveBeenNthCalledWith(2, { where: { messageId: 100, rating: -1 } })
  })

  it('无反馈时 satisfactionRate 为 null', async () => {
    mockCount.mockResolvedValueOnce(0).mockResolvedValueOnce(0)

    const stats = await feedbackService.getMessageStats(999)

    expect(stats.total).toBe(0)
    expect(stats.satisfactionRate).toBeNull()
  })
})

describe('FeedbackService.getGlobalStats', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('汇总 up/down/total + 最近 20 条负反馈评论', async () => {
    mockCount
      .mockResolvedValueOnce(50)  // total
      .mockResolvedValueOnce(35)  // up
      .mockResolvedValueOnce(15)  // down
    mockFindMany.mockResolvedValueOnce([
      { comment: '推荐不对', tags: ['推荐不相关'], createdAt: new Date('2026-06-21') },
    ])

    const stats = await feedbackService.getGlobalStats(7)

    expect(stats.totalCount).toBe(50)
    expect(stats.upCount).toBe(35)
    expect(stats.downCount).toBe(15)
    expect(stats.satisfactionRate).toBe(0.7)
    expect(stats.recentDownComments).toHaveLength(1)
    expect(stats.recentDownComments[0].comment).toBe('推荐不对')
    expect(stats.recentDownComments[0].tags).toEqual(['推荐不相关'])
  })

  it('默认 7 天窗口，days 参数生效', async () => {
    mockCount.mockResolvedValue(0)
    mockFindMany.mockResolvedValue([])

    await feedbackService.getGlobalStats(30)

    // 验证 count 用了 30 天的 since
    const where = mockCount.mock.calls[0][0].where
    expect(where.createdAt.gte).toBeDefined()
    // since 应该在 ~30 天前
    const daysAgo = (Date.now() - where.createdAt.gte.getTime()) / (1000 * 60 * 60 * 24)
    expect(daysAgo).toBeGreaterThan(29)
    expect(daysAgo).toBeLessThan(31)
  })

  it('无反馈时 satisfactionRate 为 0', async () => {
    mockCount.mockResolvedValue(0)
    mockFindMany.mockResolvedValue([])

    const stats = await feedbackService.getGlobalStats(7)

    expect(stats.satisfactionRate).toBe(0)
  })
})

describe('FeedbackService.getHighTokenLowSatisfaction', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('返回关联 message usage 的负反馈 case', async () => {
    const now = new Date()
    mockFindMany.mockResolvedValueOnce([
      // feedback.findMany（带 user include）
      {
        id: 1,
        messageId: 100,
        rating: -1,
        comment: '推荐不准',
        tags: ['推荐不准'],
        createdAt: now,
        user: { id: 10, username: 'eval-test', nickname: 'eval' },
      },
      {
        id: 2,
        messageId: 101,
        rating: -1,
        comment: '答非所问',
        tags: null,
        createdAt: now,
        user: { id: 10, username: 'eval-test', nickname: 'eval' },
      },
    ])
    mockMessageFindMany.mockResolvedValueOnce([
      { id: 100, content: 'case 1 content', metadata: { usage: { prompt: 1000, completion: 500, total: 1500 } } },
      { id: 101, content: 'case 2 content', metadata: { usage: { prompt: 3000, completion: 1000, total: 4000 } } },
    ])

    const cases = await feedbackService.getHighTokenLowSatisfaction(7, 20)

    expect(cases).toHaveLength(2)
    // 按 token total 降序
    expect(cases[0].messageId).toBe(101) // 4000
    expect(cases[0].usage?.total).toBe(4000)
    expect(cases[1].messageId).toBe(100) // 1500
  })

  it('无 usage 的 case 排最后（null 排尾部）', async () => {
    const now = new Date()
    mockFindMany.mockResolvedValueOnce([
      { id: 1, messageId: 100, rating: -1, comment: null, tags: null, createdAt: now, user: { id: 10, username: 'u', nickname: null } },
      { id: 2, messageId: 101, rating: -1, comment: null, tags: null, createdAt: now, user: { id: 10, username: 'u', nickname: null } },
    ])
    mockMessageFindMany.mockResolvedValueOnce([
      { id: 100, content: 'has usage', metadata: { usage: { prompt: 100, completion: 50, total: 150 } } },
      { id: 101, content: 'no usage', metadata: null },
    ])

    const cases = await feedbackService.getHighTokenLowSatisfaction(7, 20)
    expect(cases[0].messageId).toBe(100) // 有 usage 排前
    expect(cases[1].usage).toBeNull()
  })

  it('message 不存在则跳过该 case', async () => {
    const now = new Date()
    mockFindMany.mockResolvedValueOnce([
      { id: 1, messageId: 999, rating: -1, comment: null, tags: null, createdAt: now, user: { id: 10, username: 'u', nickname: null } },
    ])
    mockMessageFindMany.mockResolvedValueOnce([]) // 找不到 message

    const cases = await feedbackService.getHighTokenLowSatisfaction(7, 20)
    expect(cases).toHaveLength(0)
  })
})
