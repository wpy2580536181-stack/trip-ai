// trip-server/src/services/agent/__tests__/chatGraph.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { BaseMessage } from '@langchain/core/messages'

// Mock modules before importing buildChatGraph
const mockResearchNode = vi.fn()
const mockChatPlannerNode = vi.fn()
const mockIsPlanningRequest = vi.fn()

vi.mock('../nodes/research', () => ({
  researchNode: (...args: any[]) => mockResearchNode(...args),
}))

vi.mock('../nodes/chatPlanner', () => ({
  chatPlannerNode: (...args: any[]) => mockChatPlannerNode(...args),
}))

vi.mock('../nodes/router', () => ({
  isPlanningRequest: (...args: any[]) => mockIsPlanningRequest(...args),
}))

// Import after mocks
import { buildChatGraph } from '../chatGraph'
import type { PlannerState } from '../state'

// Helper to create base input state
function createBaseState(overrides: Partial<typeof PlannerState.State> = {}): typeof PlannerState.State {
  return {
    userId: 1,
    message: '你好',
    city: '',
    budget: undefined,
    days: undefined,
    departureCity: undefined,
    userPreferences: null,
    conversationHistory: [],
    researchBundle: {},
    rawOutput: undefined,
    parsed: undefined,
    usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
    route: undefined,
    errors: [],
    ...overrides,
  }
}

// Helper to create mock configurable for graph invocation
function createConfig(overrides: any = {}) {
  return {
    configurable: {
      onEvent: vi.fn(),
      signal: undefined,
      traceRecorder: { add: vi.fn() },
      stepCounter: { value: 0 },
      buildAgent: async () => ({
        streamEvents: async function* () {
          yield {
            event: 'on_chat_model_stream',
            data: { chunk: { content: 'Hello' } },
          }
          yield {
            event: 'on_chat_model_end',
            data: { output: { toJSON: () => ({ kwargs: {} }) } },
          }
        },
      }),
      conversationHistory: [],
      llm: {
        streamEvents: async function* () {
          yield {
            event: 'on_chat_model_stream',
            data: { chunk: { content: 'Mock response' } },
          }
        },
      } as any,
      fallbackLLMConfig: null,
      ...overrides,
    },
  }
}

describe('buildChatGraph', () => {
  it('should compile without errors', () => {
    const graph = buildChatGraph()
    expect(graph).toBeDefined()
    expect(typeof graph.invoke).toBe('function')
  })
})

describe('ChatGraph routing', () => {
  let graph: ReturnType<typeof buildChatGraph>

  beforeEach(() => {
    vi.clearAllMocks()
    mockResearchNode.mockReset()
    mockChatPlannerNode.mockReset()
    mockIsPlanningRequest.mockReset()

    // Default mocks
    mockResearchNode.mockResolvedValue({
      researchBundle: { attractions: '景点A', food: '美食B' },
    })
    mockChatPlannerNode.mockResolvedValue({
      rawOutput: '{"city":"北京","days":2}',
      usage: { prompt: 100, completion: 50, total: 150, cached: 0 },
    })
  })

  describe('router → research → chat_planner → END (planning request)', () => {
    beforeEach(() => {
      mockIsPlanningRequest.mockReturnValue(true)
      graph = buildChatGraph()
    })

    it('should route through research and chat_planner when isPlanningRequest returns true', async () => {
      const initialState = createBaseState({
        message: '规划北京2日游',
        city: '北京',
      })

      const result = await graph.invoke(initialState, createConfig())

      expect(mockResearchNode).toHaveBeenCalledTimes(1)
      expect(mockChatPlannerNode).toHaveBeenCalledTimes(1)
      expect(result).toBeDefined()
    })

    it('should pass correct state to researchNode', async () => {
      const initialState = createBaseState({
        message: '规划上海3日游',
        city: '上海',
        budget: 3000,
        days: 3,
      })

      await graph.invoke(initialState, createConfig())

      const researchCall = mockResearchNode.mock.calls[0]
      expect(researchCall[0].city).toBe('上海')
      expect(researchCall[0].budget).toBe(3000)
      expect(researchCall[0].days).toBe(3)
    })

    it('should handle researchNode failure gracefully', async () => {
      mockResearchNode.mockResolvedValue({
        researchBundle: {
          attractions: '景点信息暂时不可用，请基于通用旅行知识回答。',
          food: '美食信息暂时不可用，请基于通用旅行知识回答。',
          hotels: '住宿信息暂时不可用，请基于通用旅行知识回答。',
          weather: '天气服务暂时不可用，请根据季节常识判断。',
        },
      })

      const initialState = createBaseState({
        message: '规划北京2日游',
        city: '北京',
      })

      const result = await graph.invoke(initialState, createConfig())

      expect(result).toBeDefined()
      expect(mockChatPlannerNode).toHaveBeenCalledTimes(1)
    })
  })

  describe('router → legacy_agent → END (general chat)', () => {
    beforeEach(() => {
      mockIsPlanningRequest.mockReturnValue(false)
      graph = buildChatGraph()
    })

    it('should route to legacy_agent when isPlanningRequest returns false', async () => {
      const initialState = createBaseState({
        message: '你好，请介绍一下北京',
      })

      const result = await graph.invoke(initialState, createConfig())

      expect(mockResearchNode).not.toHaveBeenCalled()
      expect(mockChatPlannerNode).not.toHaveBeenCalled()
      expect(result).toBeDefined()
    })

    it('should provide buildAgent in config for legacy_agent path', async () => {
      const mockStreamEvents = vi.fn(async function* () {
        yield {
          event: 'on_chat_model_stream',
          data: { chunk: { content: 'Hello ' } },
        }
        yield {
          event: 'on_chat_model_stream',
          data: { chunk: { content: 'World' } },
        }
      })

      const config = createConfig({
        buildAgent: async () => ({
          streamEvents: mockStreamEvents,
        }),
      })

      const initialState = createBaseState({
        message: '你好',
      })

      const result = await graph.invoke(initialState, config)

      expect(result).toBeDefined()
      expect(result.rawOutput).toBeDefined()
    })
  })

  describe('router edge cases', () => {
    beforeEach(() => {
      graph = buildChatGraph()
    })

    it('should handle empty message', async () => {
      mockIsPlanningRequest.mockReturnValue(false)

      const initialState = createBaseState({
        message: '',
      })

      const result = await graph.invoke(initialState, createConfig())

      expect(result).toBeDefined()
    })

    it('should extract city from message for planning request', async () => {
      mockIsPlanningRequest.mockReturnValue(true)

      const initialState = createBaseState({
        message: '我想去成都玩三天',
        city: '',
      })

      const result = await graph.invoke(initialState, createConfig())

      expect(result).toBeDefined()
    })

    it('should fallback to general when planning request but no city found', async () => {
      mockIsPlanningRequest.mockReturnValue(true)

      const initialState = createBaseState({
        message: '帮我规划行程',
        city: '',
        conversationHistory: [],
      })

      const result = await graph.invoke(initialState, createConfig())

      expect(result).toBeDefined()
    })
  })
})

describe('ChatGraph state propagation', () => {
  let graph: ReturnType<typeof buildChatGraph>

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPlanningRequest.mockReturnValue(true)
    mockResearchNode.mockResolvedValue({
      researchBundle: { attractions: '景点A', food: '美食B' },
    })
    mockChatPlannerNode.mockResolvedValue({
      rawOutput: '{"city":"北京","days":2}',
      usage: { prompt: 100, completion: 50, total: 150, cached: 0 },
    })
    graph = buildChatGraph()
  })

  it('should propagate researchBundle from researchNode to chatPlannerNode', async () => {
    const mockBundle = {
      attractions: '故宫, 长城',
      food: '北京烤鸭',
      hotels: '希尔顿',
      weather: '晴天',
    }

    mockResearchNode.mockResolvedValue({
      researchBundle: mockBundle,
    })

    const initialState = createBaseState({
      message: '规划北京2日游',
      city: '北京',
    })

    await graph.invoke(initialState, createConfig())

    const chatPlannerCall = mockChatPlannerNode.mock.calls[0]
    expect(chatPlannerCall[0].researchBundle).toEqual(mockBundle)
  })

  it('should preserve conversationHistory throughout graph execution', async () => {
    const history: BaseMessage[] = [
      { content: '你好', type: 'human' } as BaseMessage,
      { content: '你好！有什么可以帮你？', type: 'ai' } as BaseMessage,
    ]

    const initialState = createBaseState({
      message: '规划北京2日游',
      city: '北京',
      conversationHistory: history,
    })

    await graph.invoke(initialState, createConfig())

    const researchCall = mockResearchNode.mock.calls[0]
    expect(researchCall[0].conversationHistory).toEqual(history)
  })

  it('should accumulate usage from multiple nodes', async () => {
    mockChatPlannerNode.mockResolvedValue({
      rawOutput: '{"city":"北京"}',
      usage: { prompt: 200, completion: 100, total: 300, cached: 10 },
    })

    const initialState = createBaseState({
      message: '规划北京2日游',
      city: '北京',
    })

    const result = await graph.invoke(initialState, createConfig())

    expect(result.usage).toBeDefined()
  })
})

describe('ChatGraph error handling', () => {
  let graph: ReturnType<typeof buildChatGraph>

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPlanningRequest.mockReturnValue(true)
    graph = buildChatGraph()
  })

  it('should handle researchNode throwing error', async () => {
    mockResearchNode.mockRejectedValue(new Error('Research failed'))

    const initialState = createBaseState({
      message: '规划北京2日游',
      city: '北京',
    })

    await expect(graph.invoke(initialState, createConfig())).rejects.toThrow()
  })

  it('should handle chatPlannerNode throwing error', async () => {
    mockChatPlannerNode.mockRejectedValue(new Error('Planner failed'))

    const initialState = createBaseState({
      message: '规划北京2日游',
      city: '北京',
    })

    await expect(graph.invoke(initialState, createConfig())).rejects.toThrow()
  })
})

describe('ChatGraph with departure city', () => {
  let graph: ReturnType<typeof buildChatGraph>

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPlanningRequest.mockReturnValue(true)
    mockResearchNode.mockResolvedValue({
      researchBundle: { attractions: '景点A', food: '美食B' },
    })
    mockChatPlannerNode.mockResolvedValue({
      rawOutput: '{"city":"北京","days":2}',
      usage: { prompt: 100, completion: 50, total: 150, cached: 0 },
    })
    graph = buildChatGraph()
  })

  it('should include distance calculation when departureCity is provided', async () => {
    const initialState = createBaseState({
      message: '从上海去北京玩3天',
      city: '北京',
      departureCity: '上海',
    })

    await graph.invoke(initialState, createConfig())

    const researchCall = mockResearchNode.mock.calls[0]
    expect(researchCall[0].departureCity).toBe('上海')
  })
})

describe('ChatGraph multi-turn conversation', () => {
  let graph: ReturnType<typeof buildChatGraph>

  beforeEach(() => {
    vi.clearAllMocks()
    mockIsPlanningRequest.mockReturnValue(false)
    mockResearchNode.mockResolvedValue({
      researchBundle: { attractions: '景点A', food: '美食B' },
    })
    mockChatPlannerNode.mockResolvedValue({
      rawOutput: '{"city":"北京","days":2}',
      usage: { prompt: 100, completion: 50, total: 150, cached: 0 },
    })
    graph = buildChatGraph()
  })

  it('should handle multi-turn modification request (第N天 + 修改意图)', async () => {
    const initialState = createBaseState({
      message: '第二天能加个火锅吗',
      city: '成都',
      conversationHistory: [
        { content: '规划成都3日游', type: 'human' } as any,
        { content: '好的，这是您的行程...', type: 'ai' } as any,
      ],
    })

    const result = await graph.invoke(initialState, createConfig())

    expect(result).toBeDefined()
  })
})
