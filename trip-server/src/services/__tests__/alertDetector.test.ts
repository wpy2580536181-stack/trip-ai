import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockCount = vi.fn()
const mockFindMany = vi.fn()

vi.mock('../../config/database', () => ({
  default: {
    feedback: {
      count: (...args: any[]) => mockCount(...args),
      findMany: (...args: any[]) => mockFindMany(...args),
    },
  },
}))

vi.mock('../../config/alert', () => ({
  loadAlertConfig: () => ({
    enabled: true,
    webhookUrl: 'http://test',
    webhookType: 'feishu' as const,
    threshold: 0.5,
    minFeedbacks: 5,
    intervalCron: '*/5 * * * *',
    windowMinutes: 60,
    dashboardUrl: 'http://localhost:5173',
  }),
}))

import { alertDetector } from '../alert/alertDetector'

describe('AlertDetector', () => {
  beforeEach(() => {
    mockCount.mockReset()
    mockFindMany.mockReset()
    mockFindMany.mockResolvedValue([])
  })

  it('5+ 反馈，rate < 0.5 → shouldAlert=true', async () => {
    mockCount.mockResolvedValueOnce(2)  // up
    mockCount.mockResolvedValueOnce(5)  // down
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(true)
    expect(result.stats.satisfactionRate).toBeCloseTo(0.286)  // 2/7
    expect(result.stats.feedbackCount).toBe(7)
  })

  it('5+ 反馈，rate ≥ 0.5 → shouldAlert=false', async () => {
    mockCount.mockResolvedValueOnce(6)  // up
    mockCount.mockResolvedValueOnce(2)  // down
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(false)
    expect(result.stats.satisfactionRate).toBeCloseTo(0.75)
  })

  it('< 5 反馈，rate < 0.5 → shouldAlert=false（样本太少）', async () => {
    mockCount.mockResolvedValueOnce(1)
    mockCount.mockResolvedValueOnce(2)
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(false)
    expect(result.reason).toContain('样本不足')
  })

  it('0 反馈 → shouldAlert=false', async () => {
    mockCount.mockResolvedValueOnce(0)
    mockCount.mockResolvedValueOnce(0)
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(false)
    expect(result.stats.feedbackCount).toBe(0)
  })

  it('包含 recentDownComments（取最新 5 条）', async () => {
    mockCount.mockResolvedValueOnce(1)
    mockCount.mockResolvedValueOnce(5)
    mockFindMany.mockResolvedValueOnce([
      { comment: '推荐不准', tags: ['recommend'], createdAt: new Date() },
      { comment: '太慢', tags: ['speed'], createdAt: new Date() },
    ])
    const result = await alertDetector.check()
    expect(result.stats.recentDownComments).toHaveLength(2)
    expect(result.stats.recentDownComments[0].comment).toBe('推荐不准')
  })
})
