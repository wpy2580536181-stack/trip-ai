// trip-server/src/services/agent/nodes/__tests__/chatPlanner.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AgentStreamEvent } from '../../../../types/agent'

// mock LLM
const mockStreamEvents = vi.fn()
vi.mock('../../../config/llm', () => ({
  createLLMFromConfig: () => ({ streamEvents: (...a: any[]) => mockStreamEvents(...a) }),
  loadFallbackLLMConfig: () => null,
}))

import { chatPlannerNode } from '../chatPlanner'
import { TraceRecorder } from '../../traceRecorder'

function makeConfig() {
  const events: AgentStreamEvent[] = []
  return {
    config: {
      configurable: {
        traceRecorder: new TraceRecorder(0),
        onEvent: async (e: AgentStreamEvent) => { events.push(e) },
        signal: undefined,
        stepCounter: { value: 1 },
        llm: { streamEvents: (...a: any[]) => mockStreamEvents(...a) },
        fallbackLLMConfig: null,
      },
    },
    events,
  }
}

describe('chatPlannerNode', () => {
  beforeEach(() => { mockStreamEvents.mockReset() })

  it('流式 emit chunk 事件 + 返回完整文本', async () => {
    // 模拟 LLM 流式输出 3 个 chunk
    mockStreamEvents.mockImplementation(async function* () {
      yield { event: 'on_chat_model_stream', data: { chunk: { content: '你好' } } }
      yield { event: 'on_chat_model_stream', data: { chunk: { content: '世界' } } }
      yield { event: 'on_chat_model_end', data: { output: { toJSON: () => ({ kwargs: { usage_metadata: { input_tokens: 10, output_tokens: 5, total_tokens: 15 } } }) } } }
    })

    const { config, events } = makeConfig()
    const state = {
      userId: 1, message: '帮我规划北京三日游', city: '北京',
      budget: undefined, days: 3, departureCity: undefined, userPreferences: null,
      conversationHistory: [], researchBundle: { attractions: '景点A' },
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: 'planning', errors: [],
    }

    const result = await chatPlannerNode(state as any, config)
    const chunks = events.filter(e => e.type === 'chunk')
    expect(chunks.length).toBe(2)
    expect(chunks[0].content).toBe('你好')
    expect(result.rawOutput).toBe('你好世界')
  })

  it('空 research bundle 也能工作', async () => {
    mockStreamEvents.mockImplementation(async function* () {
      yield { event: 'on_chat_model_stream', data: { chunk: { content: '回复' } } }
      yield { event: 'on_chat_model_end', data: { output: { toJSON: () => ({ kwargs: {} }) } } }
    })

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '帮我规划', city: '成都',
      budget: undefined, days: undefined, departureCity: undefined, userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: 'planning', errors: [],
    }

    const result = await chatPlannerNode(state as any, config)
    expect(result.rawOutput).toBe('回复')
  })
})
