import { describe, it, expect, vi, beforeEach } from 'vitest'

// mock 3 个工具（getWeather 在 commit f7ff287 被 MCP 替代）
const mockRetrieve = vi.fn()
const mockHotels = vi.fn()
const mockDistance = vi.fn()

vi.mock('../../tools/retrieveKnowledge', () => ({
  retrieveKnowledgeTool: { invoke: (...a: any[]) => mockRetrieve(...a) },
}))
vi.mock('../../tools/searchHotels', () => ({
  searchHotelsTool: { invoke: (...a: any[]) => mockHotels(...a) },
}))
vi.mock('../../tools/calculateDistance', () => ({
  calculateDistanceTool: { invoke: (...a: any[]) => mockDistance(...a) },
}))

import { researchNode } from '../research'
import { TraceRecorder } from '../../traceRecorder'
import type { AgentStreamEvent } from '../../../../types/agent'

function makeConfig() {
  const events: AgentStreamEvent[] = []
  const onEvent = async (e: AgentStreamEvent) => { events.push(e) }
  const traceRecorder = new TraceRecorder(0)
  return {
    config: { configurable: { traceRecorder, onEvent, signal: undefined, stepCounter: { value: 1 } } },
    events,
  }
}

describe('researchNode', () => {
  beforeEach(() => {
    mockRetrieve.mockReset()
    mockHotels.mockReset()
    mockDistance.mockReset()
  })

  it('并行调用全部 3 个工具 + distance（有 departureCity）', async () => {
    mockRetrieve.mockResolvedValue('景点A')
    mockHotels.mockResolvedValue('酒店B')
    mockDistance.mockResolvedValue('100km')

    const { config, events } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    const result = await researchNode(state as any, config)

    expect(mockRetrieve).toHaveBeenCalledTimes(2) // attractions + food
    expect(mockHotels).toHaveBeenCalledTimes(1)
    expect(mockDistance).toHaveBeenCalledTimes(1)
    expect(result.researchBundle).toMatchObject({
      attractions: '景点A', food: '景点A', hotels: '酒店B', distance: '100km',
    })
  })

  it('无 departureCity 时不调 calculate_distance', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '成都', budget: 2000, days: 2,
      departureCity: undefined, userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    expect(mockDistance).not.toHaveBeenCalled()
  })

  it('单个工具失败不影响其他工具', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockRejectedValue(new Error('酒店挂了'))
    mockDistance.mockResolvedValue('100km')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    const result = await researchNode(state as any, config)
    expect(result.researchBundle!.hotels).toContain('住宿信息暂时不可用')
    expect(result.researchBundle!.attractions).toBe('景点')
  })

  it('emit tool_start + tool_end 事件', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockDistance.mockResolvedValue('100km')

    const { config, events } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    const toolStarts = events.filter(e => e.type === 'tool_start')
    const toolEnds = events.filter(e => e.type === 'tool_end')
    expect(toolStarts.length).toBe(4) // attraction + food + hotel + distance（天气已迁移到 MCP）
    expect(toolEnds.length).toBe(4)
  })

  it('查询词带 userPreferences.interests', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockDistance.mockResolvedValue('100km')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: { interests: ['亲子', '美食'] },
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    const attractionCall = mockRetrieve.mock.calls[0][0]
    expect(attractionCall.query).toContain('亲子')
    expect(attractionCall.query).toContain('美食')
  })

  it('酒店预算拆分 = budget / days / 1.5', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockDistance.mockResolvedValue('100km')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    const hotelCall = mockHotels.mock.calls[0][0]
    expect(hotelCall.budget).toBe(Math.round(3000 / 3 / 1.5)) // 667
  })
})
