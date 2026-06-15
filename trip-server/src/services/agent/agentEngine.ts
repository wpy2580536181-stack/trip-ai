import { ChatOpenAI } from '@langchain/openai'
import { AgentExecutor, createToolCallingAgent } from '@langchain/classic/agents'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { retrieveKnowledgeTool } from './tools/retrieveKnowledge'
import { buildSystemPrompt, buildRecommendSystemPrompt } from './systemPrompt'
import { AgentStreamEvent, TripContentSchema, type TripContent } from '../../types/agent'
import { createLLM } from '../../config/llm'
import { extractJson } from '../../utils/jsonExtractor'
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
    const escaped = systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', escaped],
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

    const eventStream = executor.streamEvents(
      { input: message, chat_history: historyMessages },
      { version: 'v2' },
    )

      let fullResponse = ''
      try {
        for await (const event of eventStream as AsyncIterable<StreamEvent>) {
          if (event.event === 'on_tool_start') {
            const name = event.name || 'unknown'
            await onEvent({ type: 'tool_start', name })
          } else if (event.event === 'on_chat_model_stream') {
            const piece = this.extractTokenText(event)
            if (piece) {
              fullResponse += piece
              await onEvent({ type: 'chunk', content: piece })
            }
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

  async recommend(params: RecommendParams): Promise<{ reply: string; parsed: TripContent }> {
    const { userId, city, budget, days, onEvent } = params

    const preferences = await this.loadUserPreferences(userId)

    const systemPrompt = buildRecommendSystemPrompt({
      userPreferences: preferences,
    })

    const executor = await this.buildAgent(systemPrompt)

    const inputMessage = `请为我规划${city}${days}日游行程，预算${budget}元。`

    let rawOutput: string
    try {
      const result = await executor.invoke({
        input: inputMessage,
        chat_history: [],
      })
      rawOutput = result.output as string
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
      console.warn('[Agent] recommend JSON 解析失败，提示 agent 重试...')
      try {
        const retryResult = await executor.invoke({
          input: `你上次的输出格式有误，请严格按照JSON格式重新输出，不要添加任何markdown代码块标记。\n用户请求：${inputMessage}`,
          chat_history: [],
        })
        rawOutput = retryResult.output as string
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
