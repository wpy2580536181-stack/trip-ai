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
import { AgentStreamEvent, TripContentSchema, type TripContent, type TokenUsage } from '../../types/agent'
import { createLLM, createLLMFromConfig, loadFallbackLLMConfig, type LLMConfig } from '../../config/llm'
import { extractJson } from '../../utils/jsonExtractor'
import prisma from '../../config/database'
import { loadContext } from '../conversationService'
import { agentLog as log } from '../../utils/logger'
import { TraceRecorder } from './traceRecorder'

// 修复 P3-2：超时时间从环境变量读取，移除硬编码
const RECOMMEND_TIMEOUT_MS = Number(process.env.AGENT_RECOMMEND_TIMEOUT_MS) || 60_000
const RECOMMEND_RETRY_TIMEOUT_MS = Number(process.env.AGENT_RETRY_TIMEOUT_MS) || 30_000

export interface ChatParams {
  userId: number
  message: string
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
  signal?: AbortSignal
  /** 助手消息的 DB id，用于 AgentStep 落表 FK。tripService 预创建消息后传入。 */
  messageId: number
}

export interface RecommendParams {
  userId: number
  city: string
  budget: number
  days: number
  departureCity?: string
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
  /** Trip id（推荐场景下 message 概念弱，但若未来挂 message 可用） */
  messageId?: number
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
    signal: AbortSignal | undefined,
    traceRecorder: TraceRecorder,
    stepCounter: { value: number },
    toolStartTimes: Map<string, number>,
  ): Promise<{ content: string; usage: TokenUsage; streamStartTime: number }> {
    const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
    const streamStartTime = Date.now()

    const eventStream = executor.streamEvents(input, { version: 'v2', signal })
    let fullResponse = ''
    let streamEnabled = true

    for await (const event of eventStream as AsyncIterable<StreamEvent & { data?: any }>) {
      if (signal?.aborted) break
      if (event.event === 'on_tool_start') {
        streamEnabled = false
        const name = event.name || 'unknown'
        toolStartTimes.set(name, Date.now())
        traceRecorder.add({
          step: stepCounter.value++,
          type: 'tool_start',
          name,
          args: event.data?.input as Record<string, any> | undefined,
        })
        await onEvent({ type: 'tool_start', name })
      } else if (event.event === 'on_tool_end') {
        fullResponse = ''
        streamEnabled = true
        const name = event.name || 'unknown'
        const startTime = toolStartTimes.get(name)
        const durationMs = startTime ? Date.now() - startTime : undefined
        toolStartTimes.delete(name)
        const output = event.data?.output !== undefined
          ? JSON.stringify(event.data.output).slice(0, 10000)
          : undefined
        traceRecorder.add({
          step: stepCounter.value++,
          type: 'tool_end',
          name,
          output,
          durationMs,
        })
        await onEvent({ type: 'tool_end', name })
      } else if (event.event === 'on_chat_model_stream') {
        const piece = this.extractTokenText(event)
        if (piece && streamEnabled) {
          fullResponse += piece
          await onEvent({ type: 'chunk', content: piece })
        }
      } else if (event.event === 'on_chat_model_end') {
        // AIMessageChunk 的数据访问：直接属性 output.kwargs 是 private，
        // 必须用 toJSON().kwargs（LangChain 内部约定）
        const msg = event.data?.output as { toJSON?: () => { kwargs?: any } } | undefined
        const kwargs = msg?.toJSON?.()?.kwargs as {
          usage_metadata?: {
            input_tokens: number
            output_tokens: number
            total_tokens: number
            input_token_details?: { cache_read?: number; cache_creation?: number }
          }
          response_metadata?: {
            usage?: {
              prompt_tokens: number
              completion_tokens: number
              total_tokens: number
              prompt_tokens_details?: { cached_tokens?: number }
              prompt_cache_hit_tokens?: number
            }
          }
        } | undefined
        const um = kwargs?.usage_metadata
        const respUsage = kwargs?.response_metadata?.usage
        if (um) {
          usage.prompt += um.input_tokens ?? 0
          usage.completion += um.output_tokens ?? 0
          usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
          // LangChain usage_metadata 里 cache_read = 命中数（Anthropic 风格）
          usage.cached += um.input_token_details?.cache_read ?? 0
        } else if (respUsage) {
          usage.prompt += respUsage.prompt_tokens ?? 0
          usage.completion += respUsage.completion_tokens ?? 0
          usage.total += respUsage.total_tokens ?? (usage.prompt + usage.completion)
          // DeepSeek prompt cache：cached_tokens 或 prompt_cache_hit_tokens
          const cached = respUsage.prompt_tokens_details?.cached_tokens
            ?? respUsage.prompt_cache_hit_tokens
            ?? 0
          usage.cached += cached
        }
      }
    }

    return { content: fullResponse, usage, streamStartTime }
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
        log.warn({ err: e, fallback: 'AGNES' }, '主 LLM 失败，切换到备用模型重试')
        const fallbackLLM = createLLMFromConfig(this.fallbackLLMConfig, { streaming: false })
        const fallbackExecutor = await this.buildAgent(fallbackLLM, systemPrompt)
        return await doInvoke(fallbackExecutor)
      }
      throw e
    }
  }

  async chat(params: ChatParams) {
    const { userId, message, conversationId, onEvent, signal, messageId } = params

    const preferences = await this.loadUserPreferences(userId)

    let systemSummary: string | null = null
    let conversationRecap: string | null = null
    let historyMessages: BaseMessage[] = []

    if (conversationId) {
      const ctx = await loadContext(conversationId)
      systemSummary = ctx.systemSummary
      conversationRecap = ctx.conversationRecap
      historyMessages = this.dbMessagesToLangChain(ctx.recentMessages)
    }

    const systemPrompt = buildSystemPrompt({
      userPreferences: preferences,
      conversationSummary: systemSummary,
      conversationRecap,
    })

    const executor = await this.buildAgent(this.llm!, systemPrompt)
    const invokeInput = { chat_history: [...historyMessages, new HumanMessage(message)] }

    // 跨主备 stream 共享的 step 计数和 tool 时长
    const traceRecorder = new TraceRecorder(messageId)
    const stepCounter = { value: 1 }
    const toolStartTimes = new Map<string, number>()

    let result: { content: string; usage: TokenUsage; streamStartTime: number }
    try {
      result = await this.processStream(executor, invokeInput, onEvent, signal, traceRecorder, stepCounter, toolStartTimes)
    } catch (e) {
      if (this.fallbackLLMConfig) {
        log.warn({ err: e, fallback: 'AGNES' }, '主 LLM 失败，切换到备用模型重试')
        const fallbackLLM = createLLMFromConfig(this.fallbackLLMConfig, { streaming: true })
        const fallbackExecutor = await this.buildAgent(fallbackLLM, systemPrompt)
        try {
          result = await this.processStream(fallbackExecutor, invokeInput, onEvent, signal, traceRecorder, stepCounter, toolStartTimes)
        } catch (retryErr) {
          const errMsg = retryErr instanceof Error ? retryErr.message : '未知错误'
          log.error({ err: retryErr }, '备用模型也失败')
          traceRecorder.add({ step: stepCounter.value++, type: 'error', error: errMsg })
          await traceRecorder.flush()
          await onEvent({ type: 'error', error: errMsg })
          throw retryErr
        }
      } else {
        const errMsg = e instanceof Error ? e.message : '未知错误'
        log.error({ err: e }, 'chat 失败')
        traceRecorder.add({ step: stepCounter.value++, type: 'error', error: errMsg })
        await traceRecorder.flush()
        await onEvent({ type: 'error', error: errMsg })
        throw e
      }
    }

    // 累计 fallback 的 usage：主失败 + fallback 成功 = fallback 的 usage
    // 当前实现：主失败时 result 是 fallback 的，OK
    // 主成功：result 是主模型的 usage，OK
    traceRecorder.add({
      step: stepCounter.value++,
      type: 'complete',
      durationMs: Date.now() - result.streamStartTime,
    })
    await traceRecorder.flush()
    await onEvent({ type: 'complete', content: result.content, usage: result.usage })
    return { reply: result.content, conversationId }
  }

  async recommend(params: RecommendParams): Promise<{ reply: string; parsed: TripContent }> {
    const { userId, city, budget, days, departureCity, onEvent, messageId } = params

    const preferences = await this.loadUserPreferences(userId)

    const systemPrompt = buildRecommendSystemPrompt({
      userPreferences: preferences,
    })

    const executor = await this.buildAgent(this.llm!, systemPrompt)

    const transportHint = departureCity
      ? `（含从${departureCity}到${city}的往返交通费用）`
      : ''

    const inputMessage = `请为我规划${departureCity ? `从${departureCity}出发到` : ''}${city}${days}日游行程，预算${budget}元${transportHint}。`

    // recommend 走 invoke()（非 streamEvents），看不到 tool_start/tool_end 事件，
    // 所以只记 complete/error + duration。messageId 缺省时退化为 0（FK 失效但不影响主流程）。
    const traceRecorder = new TraceRecorder(messageId ?? 0)
    const recommendStartTime = Date.now()
    let stepCounter = 1

    let rawOutput: string
    try {
      rawOutput = await this.invokeWithFallback(
        executor, systemPrompt,
        { chat_history: [new HumanMessage(inputMessage)] },
        RECOMMEND_TIMEOUT_MS,
      )
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '未知错误'
      log.error({ err: e }, 'recommend 执行失败')
      traceRecorder.add({ step: stepCounter++, type: 'error', error: errMsg, durationMs: Date.now() - recommendStartTime })
      await traceRecorder.flush()
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
      log.warn({ err: parseErr, rawPreview: rawOutput.slice(0, 500) }, 'recommend JSON 解析失败，提示 agent 重试')
      try {
        const retryMessage =
          `你上次的输出无法通过校验：\n${zodMsg}\n\n` +
          `请严格按 system prompt 中的字段定义重新输出纯 JSON：\n` +
          `- 数字字段不加引号（city/days/totalBudget/day/budgetBreakdown.*）\n` +
          `- dailyItinerary 必须是对象数组，每天对象含 day/date/morning/afternoon/evening\n` +
          `- budgetBreakdown 必须含 accommodation/food/transportation/tickets/other 5 个数字\n` +
          `- 禁止 markdown 代码块、禁止前后缀文字\n\n` +
          `用户请求：${inputMessage}`
        rawOutput = await this.invokeWithFallback(
          executor, systemPrompt,
          { chat_history: [new HumanMessage(retryMessage)] },
          RECOMMEND_RETRY_TIMEOUT_MS,
        )
        parsed = parseAndValidate(rawOutput)
      } catch (retryErr) {
        const errMsg = 'Agent 多次输出无效 JSON，请稍后重试'
        log.error({ err: retryErr }, 'recommend JSON 重试仍失败')
        traceRecorder.add({ step: stepCounter++, type: 'error', error: errMsg, durationMs: Date.now() - recommendStartTime })
        await traceRecorder.flush()
        await onEvent({ type: 'error', error: errMsg })
        throw new Error(errMsg)
      }
    }

    traceRecorder.add({ step: stepCounter++, type: 'complete', durationMs: Date.now() - recommendStartTime })
    await traceRecorder.flush()
    await onEvent({ type: 'complete', content: rawOutput })

    return { reply: rawOutput, parsed }
  }
}

export default new AgentEngine()
