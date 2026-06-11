import { ChatOpenAI } from '@langchain/openai'
import { AgentExecutor, createReactAgent } from '@langchain/classic/agents'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages'
import { retrieveKnowledgeTool } from './tools/retrieveKnowledge'
import { buildSystemPrompt } from './systemPrompt'
import { AgentStreamEvent } from '../../types/agent'
import prisma from '../../config/database'

export interface ChatParams {
  userId: number
  message: string
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
}

export interface RecommendParams {
  userId: number
  city: string
  budget: number
  days: number
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
}

class AgentEngine {
  private llm: ChatOpenAI | null = null
  private tools = [retrieveKnowledgeTool]

  constructor() {
    this.initLLM()
  }

  private initLLM() {
    const modelProvider = process.env.MODEL_PROVIDER || 'DEEPSEEK'
    let apiKey, baseURL, model
    if (modelProvider === 'KIMI') {
      apiKey = process.env.KIMI_API_KEY
      baseURL = process.env.KIMI_BASE_URL
      model = process.env.KIMI_MODEL
    } else {
      apiKey = process.env.DEEPSEEK_API_KEY
      baseURL = process.env.DEEPSEEK_BASE_URL
      model = process.env.DEEPSEEK_MODEL
    }
    this.llm = new ChatOpenAI({
      configuration: { apiKey, baseURL },
      model,
      temperature: 0.7,
      streaming: true,
    })
  }

  private async loadUserPreferences(userId: number): Promise<Record<string, any> | null> {
    const user = await prisma.user.findUnique({ where: { id: userId }, select: { preferences: true } })
    return (user?.preferences as Record<string, any> | null) ?? null
  }

  private async buildAgent(systemPrompt: string) {
    if (!this.llm) throw new Error('LLM 未初始化')
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', systemPrompt],
      ['placeholder', '{chat_history}'],
      ['human', '{input}'],
      ['placeholder', '{agent_scratchpad}'],
    ])
    const agent = await createReactAgent({
      llm: this.llm,
      tools: this.tools,
      prompt,
    })
    return AgentExecutor.fromAgentAndTools({
      agent,
      tools: this.tools,
      verbose: false,
      handleParsingErrors: true,
    })
  }

  async chat(params: ChatParams) {
    const { userId, message, conversationId, onEvent } = params

    const preferences = await this.loadUserPreferences(userId)

    let systemSummary: string | null = null
    let historyMessages: BaseMessage[] = []
    let currentConversationId = conversationId

    if (currentConversationId) {
      const { loadContext } = await import('../conversationService')
      const ctx = await loadContext(currentConversationId)
      systemSummary = ctx.systemSummary
      historyMessages = ctx.recentMessages.map(m => {
        if (m.role === 'user') return new HumanMessage(m.content)
        if (m.role === 'assistant') return new AIMessage(m.content)
        return new SystemMessage(m.content)
      })
    }

    const systemPrompt = buildSystemPrompt({
      userPreferences: preferences,
      conversationSummary: systemSummary,
    })

    const executor = await this.buildAgent(systemPrompt)

    let fullResponse = ''
    try {
      const result = await executor.invoke({
        input: message,
        chat_history: historyMessages,
      })
      fullResponse = result.output as string
      await onEvent({ type: 'complete', content: fullResponse })
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '未知错误'
      console.error('[Agent] chat 失败:', errMsg)
      await onEvent({ type: 'error', error: errMsg })
      throw e
    }

    return { reply: fullResponse, conversationId: currentConversationId }
  }

  async recommend(params: RecommendParams) {
    const { userId, message, conversationId, onEvent } = params
    throw new Error('recommend 方法将在 Phase 1b 实现')
  }
}

export default new AgentEngine()
