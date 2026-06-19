import { ChatOpenAI } from '@langchain/openai'
import { AgentExecutor, createToolCallingAgent } from '@langchain/classic/agents'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { retrieveKnowledgeTool } from './tools/retrieveKnowledge'
import { getWeatherTool } from './tools/getWeather'
import { calculateDistanceTool } from './tools/calculateDistance'
import { searchHotelsTool } from './tools/searchHotels'
import { buildSystemPrompt, buildRecommendSystemPrompt } from './systemPrompt'
import { AgentStreamEvent, TripContentSchema, type TripContent } from '../../types/agent'
import { createLLM, createLLMFromConfig, loadFallbackLLMConfig, type LLMConfig } from '../../config/llm'
import { extractJson } from '../../utils/jsonExtractor'
import prisma from '../../config/database'
import { loadContext } from '../conversationService'

export interface ChatParams {
  userId: number
  message: string
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
  signal?: AbortSignal
}

export interface RecommendParams {
  userId: number
  city: string
  budget: number
  days: number
  departureCity?: string
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
}

class AgentEngine {
  private llm: ChatOpenAI | null = null
  private fallbackLLMConfig: LLMConfig | null = null
  private tools = [
    retrieveKnowledgeTool,
    getWeatherTool,
    calculateDistanceTool,
    searchHotelsTool,
  ]

  constructor() {
    this.llm = createLLM({ streaming: true })
    this.fallbackLLMConfig = loadFallbackLLMConfig()
  }

  private async loadUserPreferences(userId: number): Promise<Record<string, any> | null> {
    const user = await prisma.user.findUnique({ where: { id: userId }, select: { preferences: true } })
    return (user?.preferences as Record<string, any> | null) ?? null
  }

  private async buildAgent(llm: ChatOpenAI, systemPrompt: string): Promise<AgentExecutor> {
    if (!llm) throw new Error('LLM 未初始化')
    const escaped = systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', escaped],
      ['placeholder', '{chat_history}'],
      ['human', '{input}'],
      ['placeholder', '{agent_scratchpad}'],
    ])
    const agent = await createToolCallingAgent({
      llm,
      tools: this.tools,
      prompt,
    })
    return AgentExecutor.fromAgentAndTools({
      agent,
      tools: this.tools,
      verbose: false,
      handleParsingErrors: true,
      maxIterations: 8,
      earlyStoppingMethod: 'generate',
    })
  }

  private dbMessagesToLangChain(messages: { role: string; content: string }[]): BaseMessage[] {
    return messages.map(m => {
      if (m.role === 'user') return new HumanMessage(m.content)
      if (m.role === 'assistant') return new AIMessage(m.content)
      return new SystemMessage(m.content)
    })
  }

  private extractTokenText(event: StreamEvent): string | null {
    const data = event.data
    if (!data || typeof data !== 'object') return null
    const chunk = (data as { chunk?: unknown }).chunk
    if (!chunk || typeof chunk !== 'object') return null
    const text = (chunk as { content?: unknown }).content
    if (typeof text === 'string') return text
    if (Array.isArray(text)) {
      return text
        .map(part => (typeof part === 'string' ? part : (part as { text?: string })?.text ?? ''))
        .join('')
    }
    return null
  }

  private async processStream(
    executor: AgentExecutor,
    input: Record<string, unknown>,
    onEvent: (event: AgentStreamEvent) => Promise<void>,
    signal?: AbortSignal,
  ): Promise<string> {
    const eventStream = executor.streamEvents(input, { version: 'v2', signal })
    let fullResponse = ''
    let streamEnabled = true

    for await (const event of eventStream as AsyncIterable<StreamEvent>) {
      if (signal?.aborted) break
      if (event.event === 'on_tool_start') {
        streamEnabled = false
        const name = event.name || 'unknown'
        await onEvent({ type: 'tool_start', name })
      } else if (event.event === 'on_tool_end') {
        fullResponse = ''
        streamEnabled = true
        const name = event.name || 'unknown'
        await onEvent({ type: 'tool_end', name })
      } else if (event.event === 'on_chat_model_stream') {
        const piece = this.extractTokenText(event)
        if (piece && streamEnabled) {
          fullResponse += piece
          await onEvent({ type: 'chunk', content: piece })
        }
      }
    }

    return fullResponse
  }

  private async invokeWithFallback(
    executor: AgentExecutor,
    systemPrompt: string,
    input: Record<string, unknown>,
    maxTime: number,
  ): Promise<string> {
    const doInvoke = async (exec: AgentExecutor) => {
      const result = await Promise.race([
        exec.invoke(input),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error(`Agent 执行超时（${maxTime / 1000}s）`)), maxTime),
        ),
      ])
      return result.output as string
    }

    try {
      return await doInvoke(executor)
    } catch (e) {
      if (this.fallbackLLMConfig) {
        console.warn('[Agent] 主 LLM 失败，切换到备用模型重试:', e instanceof Error ? e.message : e)
        const fallbackLLM = createLLMFromConfig(this.fallbackLLMConfig, { streaming: false })
        const fallbackExecutor = await this.buildAgent(fallbackLLM, systemPrompt)
        return await doInvoke(fallbackExecutor)
      }
      throw e
    }
  }

  async chat(params: ChatParams) {
    const { userId, message, conversationId, onEvent, signal } = params

    const preferences = await this.loadUserPreferences(userId)

    let systemSummary: string | null = null
    let historyMessages: BaseMessage[] = []

    if (conversationId) {
      const ctx = await loadContext(conversationId)
      systemSummary = ctx.systemSummary
      historyMessages = this.dbMessagesToLangChain(ctx.recentMessages)
    }

    const systemPrompt = buildSystemPrompt({
      userPreferences: preferences,
      conversationSummary: systemSummary,
    })

    const executor = await this.buildAgent(this.llm!, systemPrompt)
    const invokeInput = { input: message, chat_history: historyMessages }

    let fullResponse: string
    try {
      fullResponse = await this.processStream(executor, invokeInput, onEvent, signal)
    } catch (e) {
      if (this.fallbackLLMConfig) {
        console.warn('[Agent] 主 LLM 失败，切换到备用模型重试:', e instanceof Error ? e.message : e)
        const fallbackLLM = createLLMFromConfig(this.fallbackLLMConfig, { streaming: true })
        const fallbackExecutor = await this.buildAgent(fallbackLLM, systemPrompt)
        try {
          fullResponse = await this.processStream(fallbackExecutor, invokeInput, onEvent, signal)
        } catch (retryErr) {
          const errMsg = retryErr instanceof Error ? retryErr.message : '未知错误'
          console.error('[Agent] 备用模型也失败:', errMsg)
          await onEvent({ type: 'error', error: errMsg })
          throw retryErr
        }
      } else {
        const errMsg = e instanceof Error ? e.message : '未知错误'
        console.error('[Agent] chat 失败:', errMsg)
        await onEvent({ type: 'error', error: errMsg })
        throw e
      }
    }

    await onEvent({ type: 'complete', content: fullResponse })
    return { reply: fullResponse, conversationId }
  }

  async recommend(params: RecommendParams): Promise<{ reply: string; parsed: TripContent }> {
    const { userId, city, budget, days, departureCity, onEvent } = params

    const preferences = await this.loadUserPreferences(userId)

    const systemPrompt = buildRecommendSystemPrompt({
      userPreferences: preferences,
    })

    const executor = await this.buildAgent(this.llm!, systemPrompt)

    const transportHint = departureCity
      ? `（含从${departureCity}到${city}的往返交通费用）`
      : ''

    const inputMessage = `请为我规划${departureCity ? `从${departureCity}出发到` : ''}${city}${days}日游行程，预算${budget}元${transportHint}。`

    let rawOutput: string
    try {
      rawOutput = await this.invokeWithFallback(
        executor, systemPrompt,
        { input: inputMessage, chat_history: [] },
        60_000,
      )
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '未知错误'
      console.error('[Agent] recommend 执行失败:', errMsg)
      await onEvent({ type: 'error', error: errMsg })
      throw e
    }

    const parseAndValidate = (text: string): TripContent => {
      return TripContentSchema.parse(extractJson(text))
    }

    let parsed: TripContent
    try {
      parsed = parseAndValidate(rawOutput)
    } catch (parseErr) {
      const zodMsg = parseErr instanceof Error ? parseErr.message : String(parseErr)
      console.warn('[Agent] recommend JSON 解析失败，提示 agent 重试...')
      console.warn('[Agent] parse error:', zodMsg)
      console.warn('[Agent] raw output (first 500 chars):', rawOutput.slice(0, 500))
      try {
        rawOutput = await this.invokeWithFallback(
          executor, systemPrompt,
          { input: `你上次的输出格式有误，请严格按照JSON格式重新输出，不要添加任何markdown代码块标记。\n用户请求：${inputMessage}`, chat_history: [] },
          30_000,
        )
        parsed = parseAndValidate(rawOutput)
      } catch (retryErr) {
        const errMsg = 'Agent 多次输出无效 JSON，请稍后重试'
        console.error('[Agent] recommend JSON 重试仍失败:', retryErr)
        await onEvent({ type: 'error', error: errMsg })
        throw new Error(errMsg)
      }
    }

    await onEvent({ type: 'complete', content: rawOutput })

    return { reply: rawOutput, parsed }
  }
}

export default new AgentEngine()
