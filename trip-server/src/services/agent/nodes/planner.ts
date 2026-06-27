// trip-server/src/services/agent/nodes/planner.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { ChatOpenAI } from '@langchain/openai'
import { createLLMFromConfig, loadFallbackLLMConfig } from '../../../config/llm'
import { buildPlannerPrompt } from '../plannerPrompt'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'
import type { TokenUsage } from '../../../types/agent'
import { buildRetryMessage } from './validate'

const RECOMMEND_TIMEOUT_MS = Number(process.env.AGENT_RECOMMEND_TIMEOUT_MS) || 60_000
const RECOMMEND_RETRY_TIMEOUT_MS = Number(process.env.AGENT_RETRY_TIMEOUT_MS) || 30_000

/** 从 AIMessage 结果对象中提取 token usage，兼容 usage_metadata 与 response_metadata.usage 两种来源 */
function extractUsageFromResult(result: any): TokenUsage {
  const um = result?.usage_metadata
  const ru = result?.response_metadata?.usage
  const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
  if (um) {
    usage.prompt += um.input_tokens ?? 0
    usage.completion += um.output_tokens ?? 0
    usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += um.input_token_details?.cache_read ?? 0
  } else if (ru) {
    usage.prompt += ru.prompt_tokens ?? 0
    usage.completion += ru.completion_tokens ?? 0
    usage.total += ru.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += ru.prompt_tokens_details?.cached_tokens ?? ru.prompt_cache_hit_tokens ?? 0
  }
  return usage
}

async function invokeLLM(
  llm: ChatOpenAI,
  systemPrompt: string,
  userMessage: string,
  timeout: number,
): Promise<{ content: string; usage: TokenUsage }> {
  const prompt = ChatPromptTemplate.fromMessages([
    ['system', systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')],
    ['human', '{input}'],
  ])
  const chain = prompt.pipe(llm)
  const result = await Promise.race([
    chain.invoke({ input: userMessage }),
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`planner 执行超时（${timeout / 1000}s）`)), timeout),
    ),
  ])
  const content = (result as { content: string }).content
  const usage = extractUsageFromResult(result)
  return { content, usage }
}

export async function plannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
    llm: ChatOpenAI
    fallbackLLMConfig: ReturnType<typeof loadFallbackLLMConfig>
  }

  const systemPrompt = buildPlannerPrompt({
    city: state.city,
    budget: state.budget,
    days: state.days,
    departureCity: state.departureCity,
    userPreferences: state.userPreferences,
    researchBundle: state.researchBundle,
  })

  const userMessage = state.message || `请为我规划${state.departureCity ? `从${state.departureCity}出发到` : ''}${state.city}${state.days}日游行程，预算${state.budget}元。`

  let result: { content: string; usage: TokenUsage }
  try {
    result = await invokeLLM(llm, systemPrompt, userMessage, RECOMMEND_TIMEOUT_MS)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: false })
      result = await invokeLLM(fallbackLLM, systemPrompt, userMessage, RECOMMEND_TIMEOUT_MS)
    } else {
      throw e
    }
  }

  return { rawOutput: result.content, usage: result.usage }
}

export async function retryPlannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
    llm: ChatOpenAI
    fallbackLLMConfig: ReturnType<typeof loadFallbackLLMConfig>
  }

  const systemPrompt = buildPlannerPrompt({
    city: state.city,
    budget: state.budget,
    days: state.days,
    departureCity: state.departureCity,
    userPreferences: state.userPreferences,
    researchBundle: state.researchBundle,
  })

  const retryMessage = buildRetryMessage(
    state.errors[state.errors.length - 1] ?? '校验失败',
    state.message || `规划${state.city}${state.days}日游`,
  )

  let result: { content: string; usage: TokenUsage }
  try {
    result = await invokeLLM(llm, systemPrompt, retryMessage, RECOMMEND_RETRY_TIMEOUT_MS)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: false })
      result = await invokeLLM(fallbackLLM, systemPrompt, retryMessage, RECOMMEND_RETRY_TIMEOUT_MS)
    } else {
      throw e
    }
  }

  return { rawOutput: result.content, usage: result.usage }
}