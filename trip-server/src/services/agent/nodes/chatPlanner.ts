// trip-server/src/services/agent/nodes/chatPlanner.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { ChatOpenAI } from '@langchain/openai'
import { SystemMessage, HumanMessage, AIMessage, ToolMessage, type BaseMessage } from '@langchain/core/messages'
import { buildChatPlannerStaticPrompt } from '../plannerPrompt'
import { createLLMFromConfig, loadFallbackLLMConfig } from '../../../config/llm'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'
import type { TokenUsage } from '../../../types/agent'
import type { ResearchBundle } from '../types'

const TOOL_NAMES: Record<string, string> = {
  attractions: 'retrieve_knowledge',
  food: 'retrieve_knowledge',
  hotels: 'search_hotels',
  distance: 'calculate_distance',
  weather: 'maps_weather',
}

/** 把 researchNode 的 bundle 转成标准 tool call 协议消息（AIMessage.tool_calls + ToolMessage） */
function buildToolCallMessages(bundle: ResearchBundle): BaseMessage[] {
  const entries = Object.entries(bundle).filter(([, v]) => v && typeof v === 'string') as [string, string][]
  if (entries.length === 0) return []

  const callIdBase = `call_research_${Date.now()}_`

  // 一条 AIMessage 携带多个 tool_calls（LLM 真实调工具时也一个 message 包含所有并行调用）
  const toolCallMsg = new AIMessage({
    content: '',
    tool_calls: entries.map(([key], i) => ({
      id: `${callIdBase}${i}_${key}`,
      name: TOOL_NAMES[key] || 'retrieve_knowledge',
      args: {},
    })),
  })

  // 每条工具结果对应一条 ToolMessage
  const toolMsgs = entries.map(([key, value], i) => new ToolMessage({
    tool_call_id: `${callIdBase}${i}_${key}`,
    name: TOOL_NAMES[key] || 'retrieve_knowledge',
    content: value,
  }))

  return [toolCallMsg, ...toolMsgs]
}

function extractTokenText(event: StreamEvent): string | null {
  const data = event.data
  if (!data || typeof data !== 'object') return null
  const chunk = (data as { chunk?: unknown }).chunk
  if (!chunk || typeof chunk !== 'object') return null
  const text = (chunk as { content?: unknown }).content
  if (typeof text === 'string') return text
  if (Array.isArray(text)) {
    return text.map(part => (typeof part === 'string' ? part : (part as { text?: string })?.text ?? '')).join('')
  }
  return null
}

function extractUsage(event: StreamEvent, usage: TokenUsage): void {
  const msg = event.data?.output as { toJSON?: () => { kwargs?: any } } | undefined
  const kwargs = msg?.toJSON?.()?.kwargs as {
    usage_metadata?: { input_tokens: number; output_tokens: number; total_tokens: number; input_token_details?: { cache_read?: number } }
    response_metadata?: { usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number; prompt_tokens_details?: { cached_tokens?: number }; prompt_cache_hit_tokens?: number } }
  } | undefined

  const um = kwargs?.usage_metadata
  const respUsage = kwargs?.response_metadata?.usage
  if (um) {
    usage.prompt += um.input_tokens ?? 0
    usage.completion += um.output_tokens ?? 0
    usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += um.input_token_details?.cache_read ?? 0
  } else if (respUsage) {
    usage.prompt += respUsage.prompt_tokens ?? 0
    usage.completion += respUsage.completion_tokens ?? 0
    usage.total += respUsage.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += respUsage.prompt_tokens_details?.cached_tokens ?? respUsage.prompt_cache_hit_tokens ?? 0
  }
}

export async function chatPlannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { onEvent, signal, llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
    llm: ChatOpenAI
    fallbackLLMConfig: ReturnType<typeof loadFallbackLLMConfig>
  }

  // system prompt 纯静态（不依赖 RAG/用户输入），跨轮字节稳定
  const systemPrompt = buildChatPlannerStaticPrompt()
  const escaped = systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')

  // research bundle → 标准 tool call 协议消息
  const toolMessages = buildToolCallMessages(state.researchBundle)

  const fullMessages: BaseMessage[] = [
    new SystemMessage(escaped),
    ...(state.conversationHistory ?? []),
    ...toolMessages,
    new HumanMessage(state.message),
  ]

  const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
  let fullResponse = ''

  async function runStream(currentLlm: ChatOpenAI): Promise<void> {
    const eventStream = currentLlm.streamEvents(fullMessages, { version: 'v2', signal })
    for await (const event of eventStream as AsyncIterable<StreamEvent & { data?: any }>) {
      if (signal?.aborted) break
      if (event.event === 'on_chat_model_stream') {
        const piece = extractTokenText(event)
        if (piece) {
          fullResponse += piece
          await onEvent({ type: 'chunk', content: piece })
        }
      } else if (event.event === 'on_chat_model_end') {
        extractUsage(event, usage)
      }
    }
  }

  try {
    await runStream(llm)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: true })
      await runStream(fallbackLLM)
    } else {
      throw e
    }
  }

  return { rawOutput: fullResponse, usage }
}
