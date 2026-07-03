// trip-server/src/services/agent/__tests__/plannerGraph.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockResearch = vi.fn()
const mockPlanner = vi.fn()
const mockRetry = vi.fn()

vi.mock('../nodes/research', () => ({
  researchNode: (...a: any[]) => mockResearch(...a),
}))
vi.mock('../nodes/planner', () => ({
  plannerNode: (...a: any[]) => mockPlanner(...a),
  retryPlannerNode: (...a: any[]) => mockRetry(...a),
}))
vi.mock('../nodes/validate', () => ({
  validateWithRepair: vi.fn((raw: string) => {
    // 简单模拟：raw 包含 'invalid' 时抛错
    if (raw.includes('invalid')) throw new Error('bad json')
    return { parsed: { city: '北京', days: 2 }, repaired: false }
  }),
}))

import { buildPlannerGraph } from '../plannerGraph'

const baseInput = {
  userId: 1, message: '规划北京2日游', city: '北京',
  budget: 2000, days: 2, departureCity: undefined,
  userPreferences: null, conversationHistory: [],
  researchBundle: {}, rawOutput: undefined, parsed: undefined,
  usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
  route: undefined, errors: [],
} as any

describe('plannerGraph', () => {
  beforeEach(() => {
    mockResearch.mockReset()
    mockPlanner.mockReset()
    mockRetry.mockReset()
  })

  it('合法输出 → research → planner → validate → END（不重试）', async () => {
    mockResearch.mockResolvedValue({ researchBundle: { attractions: '景点A' } })
    mockPlanner.mockResolvedValue({ rawOutput: '{"city":"北京"}' })

    const graph = buildPlannerGraph()
    const result = await graph.invoke(baseInput, { configurable: {} })

    expect(mockResearch).toHaveBeenCalledTimes(1)
    expect(mockPlanner).toHaveBeenCalledTimes(1)
    expect(mockRetry).not.toHaveBeenCalled()
    expect(result.parsed).toEqual({ city: '北京', days: 2 })
  })

  it('非法输出 → research → planner → validate → retry → END', async () => {
    mockResearch.mockResolvedValue({ researchBundle: {} })
    mockPlanner.mockResolvedValue({ rawOutput: 'invalid json' })
    mockRetry.mockResolvedValue({ rawOutput: '{"city":"北京"}' })

    const graph = buildPlannerGraph()
    const result = await graph.invoke(baseInput, { configurable: {} })

    expect(mockRetry).toHaveBeenCalledTimes(1)
    // 拓扑为 retry_planner → END，外层 recommend() 再做二次校验；
    // 图本身不再 validate，故 parsed 仍为 undefined，rawOutput 携带重试输出。
    expect(result.parsed).toBeUndefined()
    expect(result.rawOutput).toEqual('{"city":"北京"}')
  })
})