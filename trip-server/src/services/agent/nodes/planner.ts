// trip-server/src/services/agent/nodes/planner.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { ChatOpenAI } from '@langchain/openai'
import { createLLMFromConfig, loadFallbackLLMConfig } from '../../../config/llm'
import { buildPlannerPrompt } from '../plannerPrompt'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'
import { emptyUsage } from '../types'
import type { TokenUsage } from '../../../types/agent'
import { buildRetryMessage } from './validate'

const RECOMMEND_TIMEOUT_MS = Number(process.env.AGENT_RECOMMEND_TIMEOUT_MS) || 60_000
const RECOMMEND_RETRY_TIMEOUT_MS = Number(process.env.AGENT_RETRY_TIMEOUT_MS) || 30_000

async function invokeLLM(
  llm: ChatOpenAI,
  systemPrompt: string,
  userMessage: string,
  timeout: number,
): Promise<string> {
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
  return (result as { content: string }).content
}

export async function plannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { traceRecorder, stepCounter, llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
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

  traceRecorder.add({ step: stepCounter.value++, type: 'chunk' })

  let rawOutput: string
  try {
    rawOutput = await invokeLLM(llm, systemPrompt, userMessage, RECOMMEND_TIMEOUT_MS)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: false })
      rawOutput = await invokeLLM(fallbackLLM, systemPrompt, userMessage, RECOMMEND_TIMEOUT_MS)
    } else {
      throw e
    }
  }

  return { rawOutput }
}

export async function retryPlannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { traceRecorder, stepCounter, llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
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

  traceRecorder.add({ step: stepCounter.value++, type: 'chunk' })

  let rawOutput: string
  try {
    rawOutput = await invokeLLM(llm, systemPrompt, retryMessage, RECOMMEND_RETRY_TIMEOUT_MS)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: false })
      rawOutput = await invokeLLM(fallbackLLM, systemPrompt, retryMessage, RECOMMEND_RETRY_TIMEOUT_MS)
    } else {
      throw e
    }
  }

  return { rawOutput }
}