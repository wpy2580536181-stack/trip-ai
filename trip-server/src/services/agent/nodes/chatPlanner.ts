// trip-server/src/services/agent/nodes/chatPlanner.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { ChatOpenAI } from '@langchain/openai'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { buildChatPlannerPrompt } from '../plannerPrompt'
import { createLLMFromConfig, loadFallbackLLMConfig } from '../../../config/llm'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'
import type { TokenUsage } from '../../../types/agent'

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

  const systemPrompt = buildChatPlannerPrompt({
    city: state.city,
    budget: state.budget,
    days: state.days,
    departureCity: state.departureCity,
    userPreferences: state.userPreferences,
    researchBundle: state.researchBundle,
  })

  const escaped = systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')
  const prompt = ChatPromptTemplate.fromMessages([
    ['system', escaped],
    ['human', '{input}'],
  ])

  const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
  let fullResponse = ''

  async function runStream(currentLlm: ChatOpenAI): Promise<void> {
    const messages = await prompt.formatMessages({ input: state.message })
    const eventStream = currentLlm.streamEvents(messages, { version: 'v2', signal })
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
