import { ChatOpenAI } from '@langchain/openai'
import { AgentExecutor, createToolCallingAgent } from '@langchain/classic/agents'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages'
import { retrieveKnowledgeTool } from './tools/retrieveKnowledge'
import { calculateDistanceTool } from './tools/calculateDistance'
import { searchHotelsTool } from './tools/searchHotels'
import { DynamicTool } from '@langchain/core/tools'
import { loadAmapTools } from '../mcp/amapMcpToolLoader'
import { buildSystemPrompt } from './systemPrompt'
import { AgentStreamEvent, type TripContent } from '../../types/agent'
import { createLLM, loadFallbackLLMConfig, type LLMConfig } from '../../config/llm'
import prisma from '../../config/database'
import { loadContext } from '../conversationService'
import { agentLog as log } from '../../utils/logger'
import { TraceRecorder } from './traceRecorder'
import { buildPlannerGraph } from './plannerGraph'
import { buildChatGraph } from './chatGraph'
import { validateOutput } from './nodes/validate'
import { emptyUsage } from './types'
import { ToolCache } from '../llmGuard/toolCache'
import { withToolCache } from './toolCache'

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

  /**
   * Tool 结果缓存（per-tool 独立 TTL + size）
   * - get_weather: 30 分钟，字面归一化（城市名稳定）
   * - retrieve_knowledge: 6 小时，**embedding 归一化**（query 字面多变但语义同）
   * - search_hotels / calculate_distance: 不加（计算成本低/组合爆炸）
   *
   * embedding 归一化用 bge-small-zh-v1.5（本地，~50ms/query）。
   * 阈值 0.85：同义改写通常 > 0.85，跨主题 < 0.7。
   */
  private toolCache = new ToolCache({
    retrieve_knowledge: {
      ttlMs: 6 * 60 * 60 * 1000,
      maxSize: 500,
      embeddingKey: {
        // 把 city + category + query 拼成"语义字符串"再 embedding
        // 这样"成都美食 food"和"北京美食 food"不会被误命中
        extractor: (args) => `${args.city ?? ''} ${args.category ?? ''} ${args.query ?? ''}`.trim(),
        threshold: 0.85,
      },
    },
  })

  private amapTools: DynamicTool[] = []
  private amapToolsInitPromise: Promise<void> | null = null

  get tools() {
    return [
      withToolCache(retrieveKnowledgeTool, { cache: this.toolCache, toolName: 'retrieve_knowledge' }),
      searchHotelsTool,
      calculateDistanceTool,
      ...this.amapTools,
    ]
  }

  async ensureAmapTools(): Promise<void> {
    if (!this.amapToolsInitPromise) {
      this.amapToolsInitPromise = (async () => {
        this.amapTools = await loadAmapTools()
      })()
    }
    return this.amapToolsInitPromise
  }

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

  async chat(params: ChatParams) {
    await this.ensureAmapTools()
    const { userId, message, conversationId, onEvent, signal, messageId } = params

    const startTime = Date.now()
    const preferences = await this.loadUserPreferences(userId)

    let systemSummary: string | null = null
    let conversationRecap: string | null = null
    let conversationHistory: BaseMessage[] = []

    if (conversationId) {
      const ctx = await loadContext(conversationId)
      systemSummary = ctx.systemSummary
      conversationRecap = ctx.conversationRecap
      conversationHistory = this.dbMessagesToLangChain(ctx.recentMessages)
    }

    const systemPrompt = buildSystemPrompt({
      userPreferences: preferences,
      conversationSummary: systemSummary,
      conversationRecap,
    })

    // 跨主备 stream 共享的 step 计数
    const traceRecorder = new TraceRecorder(messageId)
    const stepCounter = { value: 1 }

    const graph = buildChatGraph()
    const config = {
      configurable: {
        traceRecorder,
        onEvent,
        signal,
        stepCounter,
        llm: this.llm,
        fallbackLLMConfig: this.fallbackLLMConfig,
        // legacy agent 节点用：闭包捕获当前 systemPrompt，惰性构建 AgentExecutor
        buildAgent: () => this.buildAgent(this.llm!, systemPrompt),
        systemPrompt,
        conversationHistory,
      },
    }

    const initialState = {
      userId,
      message,
      city: '北京', // router 节点会按消息内容覆盖
      budget: undefined,
      days: undefined,
      departureCity: undefined,
      userPreferences: preferences,
      conversationHistory,
      researchBundle: {},
      rawOutput: undefined,
      parsed: undefined,
      usage: emptyUsage(),
      route: undefined,
      errors: [],
    }

    try {
      const result = await graph.invoke(initialState, config)
      traceRecorder.add({ step: stepCounter.value++, type: 'complete', durationMs: Date.now() - startTime })
      await traceRecorder.flush()
      await onEvent({
        type: 'complete',
        content: result.rawOutput ?? '',
        usage: result.usage,
      })
      return { reply: result.rawOutput ?? '', conversationId }
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '未知错误'
      log.error({ err: e }, 'chat 失败')
      traceRecorder.add({ step: stepCounter.value++, type: 'error', error: errMsg })
      await traceRecorder.flush()
      await onEvent({ type: 'error', error: errMsg })
      throw e
    }
  }

  async recommend(params: RecommendParams): Promise<{ reply: string; parsed: TripContent }> {
    await this.ensureAmapTools()
    const { userId, city, budget, days, departureCity, onEvent, messageId } = params

    const startTime = Date.now()
    const preferences = await this.loadUserPreferences(userId)

    const traceRecorder = new TraceRecorder(messageId ?? 0)
    const stepCounter = { value: 1 }

    const inputMessage = `请为我规划${departureCity ? `从${departureCity}出发到` : ''}${city}${days}日游行程，预算${budget}元。`

    const graph = buildPlannerGraph()
    const config = {
      configurable: {
        traceRecorder,
        onEvent,
        signal: undefined,
        stepCounter,
        llm: this.llm,
        fallbackLLMConfig: this.fallbackLLMConfig,
      },
    }

    const initialState = {
      userId,
      message: inputMessage,
      city,
      budget,
      days,
      departureCity,
      userPreferences: preferences,
      conversationHistory: [] as BaseMessage[],
      researchBundle: {},
      rawOutput: undefined,
      parsed: undefined,
      usage: emptyUsage(),
      route: undefined,
      errors: [],
    }

    try {
      const result = await graph.invoke(initialState, config)
      // plannerGraph 的 retry_planner 后直接 END，未再跑 validate 节点，
      // 故在此对最终 rawOutput 做一次校验，拿到解析结果或抛错。
      if (result.parsed) {
        traceRecorder.add({ step: stepCounter.value++, type: 'complete', durationMs: Date.now() - startTime })
        await traceRecorder.flush()
        await onEvent({ type: 'complete', content: result.rawOutput ?? '', usage: result.usage })
        return { reply: result.rawOutput ?? '', parsed: result.parsed }
      }
      // retry 后 rawOutput 仍可能未过校验，二次校验一次
      try {
        const { parsed } = validateOutput(result.rawOutput!)
        traceRecorder.add({ step: stepCounter.value++, type: 'complete', durationMs: Date.now() - startTime })
        await traceRecorder.flush()
        await onEvent({ type: 'complete', content: result.rawOutput ?? '', usage: result.usage })
        return { reply: result.rawOutput ?? '', parsed }
      } catch {
        throw new Error('Agent 多次输出无效 JSON，请稍后重试')
      }
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '未知错误'
      log.error({ err: e }, 'recommend 执行失败')
      traceRecorder.add({ step: stepCounter.value++, type: 'error', error: errMsg })
      await traceRecorder.flush()
      await onEvent({ type: 'error', error: errMsg })
      throw e
    }
  }
}

const agentEngine = new AgentEngine()
export default agentEngine
export const ensureAmapTools = agentEngine.ensureAmapTools.bind(agentEngine)
