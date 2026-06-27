// trip-server/src/services/agent/__tests__/chatGraph.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AgentStreamEvent } from '../../../types/agent'

const mockResearch = vi.fn()
const mockChatPlanner = vi.fn()
const mockLegacyAgent = vi.fn()
const mockBuildAgent = vi.fn()

vi.mock('../nodes/research', () => ({
  researchNode: (...a: any[]) => mockResearch(...a),
}))
vi.mock('../nodes/chatPlanner', () => ({
  chatPlannerNode: (...a: any[]) => mockChatPlanner(...a),
}))

import { buildChatGraph } from '../chatGraph'

function makeConfig(legacyExecutor?: any) {
  const events: AgentStreamEvent[] = []
  return {
    config: {
      configurable: {
        traceRecorder: { add: vi.fn(), flush: vi.fn() },
        onEvent: async (e: AgentStreamEvent) => { events.push(e) },
        signal: undefined,
        stepCounter: { value: 1 },
        llm: {},
        fallbackLLMConfig: null,
        legacyExecutor: legacyExecutor ?? mockLegacyAgent(),
        buildAgent: mockBuildAgent,
      },
    },
    events,
  }
}

function makeState(message: string, city = '北京') {
  return {
    userId: 1, message, city,
    budget: undefined, days: undefined, departureCity: undefined,
    userPreferences: null, conversationHistory: [],
    researchBundle: {}, rawOutput: undefined, parsed: undefined,
    usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
    route: undefined, errors: [],
  } as any
}

describe('chatGraph', () => {
  beforeEach(() => {
    mockResearch.mockReset()
    mockChatPlanner.mockReset()
    mockLegacyAgent.mockReset()
    mockBuildAgent.mockReset()
  })

  it('planning 路由 → research → chatPlanner', async () => {
    mockResearch.mockResolvedValue({ researchBundle: { attractions: 'A' } })
    mockChatPlanner.mockResolvedValue({ rawOutput: '规划完成', usage: { prompt: 0, completion: 0, total: 0, cached: 0 } })
    mockBuildAgent.mockReturnValue({ invoke: vi.fn() })

    const graph = buildChatGraph()
    const { config } = makeConfig()
    await graph.invoke(makeState('帮我规划北京三日游行程'), config)

    expect(mockResearch).toHaveBeenCalledTimes(1)
    expect(mockChatPlanner).toHaveBeenCalledTimes(1)
    expect(mockBuildAgent).not.toHaveBeenCalled()
  })

  it('general 路由 → legacy agent', async () => {
    const legacyExecutor = {
      invoke: vi.fn().mockResolvedValue({ output: '晴天' }),
      streamEvents: async function* () {
        yield { event: 'on_chat_model_stream', data: { chunk: { content: '晴天' } } }
      },
    }
    mockBuildAgent.mockReturnValue(legacyExecutor)

    const graph = buildChatGraph()
    const { config } = makeConfig(legacyExecutor)
    const result = await graph.invoke(makeState('北京今天天气怎么样'), config)

    expect(mockResearch).not.toHaveBeenCalled()
    expect(mockChatPlanner).not.toHaveBeenCalled()
    expect(mockBuildAgent).toHaveBeenCalledTimes(1)
    expect(result.rawOutput).toBeDefined()
  })
})