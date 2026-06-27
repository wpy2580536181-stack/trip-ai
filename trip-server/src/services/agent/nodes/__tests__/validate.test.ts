// trip-server/src/services/agent/nodes/__tests__/validate.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../../../utils/jsonExtractor', () => ({
  extractJson: (text: string) => {
    try { return JSON.parse(text) } catch { throw new Error('JSON parse failed') }
  },
}))

import { validateOutput, buildRetryMessage } from '../validate'

describe('validateOutput', () => {
  it('合法 JSON + 字段齐全 → parse 成功', () => {
    const raw = JSON.stringify({
      city: '北京', days: 2, totalBudget: 3000,
      dailyItinerary: [
        { day: 1, date: '', morning: { spot: 'A' }, afternoon: { spot: 'B' }, evening: { spot: 'C' } },
        { day: 2, date: '', morning: { spot: 'D' }, afternoon: { spot: 'E' }, evening: { spot: 'F' } },
      ],
      budgetBreakdown: { accommodation: 1000, food: 500, transportation: 500, tickets: 500, other: 500 },
      tips: ['带伞'],
    })
    const result = validateOutput(raw)
    expect(result.parsed.city).toBe('北京')
    expect(result.parsed.days).toBe(2)
  })

  it('非法 JSON → 抛错', () => {
    expect(() => validateOutput('not json')).toThrow()
  })

  it('缺字段 → 抛 Zod 错', () => {
    const raw = JSON.stringify({ city: '北京' }) // 缺 days/dailyItinerary 等
    expect(() => validateOutput(raw)).toThrow()
  })
})

describe('buildRetryMessage', () => {
  it('包含 zod 错误信息', () => {
    const msg = buildRetryMessage('zod error here', '帮我规划北京三日游')
    expect(msg).toContain('zod error here')
    expect(msg).toContain('北京三日游')
  })
})