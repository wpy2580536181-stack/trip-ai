import { ChatOpenAI } from '@langchain/openai'
import { AgentExecutor, createToolCallingAgent } from '@langchain/classic/agents'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages'
import { retrieveKnowledgeTool } from './tools/retrieveKnowledge'
import { buildSystemPrompt } from './systemPrompt'
import { AgentStreamEvent } from '../../types/agent'
import { createLLM } from '../../config/llm'
import prisma from '../../config/database'
import { loadContext } from '../conversationService'

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

type AgentStep = {
  intermediateSteps?: Array<{ action: { tool: string }; observation: string }>
  returnValues?: Record<string, unknown>
  output?: string
  [key: string]: unknown
}

class AgentEngine {
  private llm: ChatOpenAI | null = null
  private tools = [retrieveKnowledgeTool]

  constructor() {
    this.llm = createLLM({ streaming: true })
  }

  private async loadUserPreferences(userId: number): Promise<Record<string, any> | null> {
    const user = await prisma.user.findUnique({ where: { id: userId }, select: { preferences: true } })
    return (user?.preferences as Record<string, any> | null) ?? null
  }

  private async buildAgent(systemPrompt: string): Promise<AgentExecutor> {
    if (!this.llm) throw new Error('LLM 未初始化')
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', systemPrompt],
      ['placeholder', '{chat_history}'],
      ['human', '{input}'],
      ['placeholder', '{agent_scratchpad}'],
    ])
    const agent = await createToolCallingAgent({
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

  private dbMessagesToLangChain(messages: { role: string; content: string }[]): BaseMessage[] {
    return messages.map(m => {
      if (m.role === 'user') return new HumanMessage(m.content)
      if (m.role === 'assistant') return new AIMessage(m.content)
      return new SystemMessage(m.content)
    })
  }

  async chat(params: ChatParams) {
    const { userId, message, conversationId, onEvent } = params

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

    const executor = await this.buildAgent(systemPrompt)

    const stream = await executor.stream({
      input: message,
      chat_history: historyMessages,
    })

      let fullResponse = ''
      try {
        for await (const chunk of stream as AsyncIterable<AgentStep>) {
          if (chunk.output != null) {
            const piece = String(chunk.output)
            fullResponse += piece
            await onEvent({ type: 'chunk', content: piece })
          }
        }
        await onEvent({ type: 'complete', content: fullResponse })
      } catch (e) {
        const errMsg = e instanceof Error ? e.message : '未知错误'
        console.error('[Agent] chat 失败:', errMsg)
        await onEvent({ type: 'error', error: errMsg })
        throw e
      }

      return { reply: fullResponse, conversationId }
    }

  async recommend(params: RecommendParams): Promise<never> {
    void params
    throw new Error('recommend 方法将在 Phase 1b 实现')
  }
}

export default new AgentEngine()
