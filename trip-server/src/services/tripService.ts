import agentEngine from './agent/agentEngine'
import { getOrCreateConversation, saveMessage } from './conversationService'
import { AgentStreamEvent } from '../types/agent'

class TripService {
  async chat(params: {
    userId: number
    message: string
    conversationId?: number
  }) {
    const { userId, message, conversationId } = params

    const conversation = await getOrCreateConversation(userId, conversationId)
    await saveMessage(conversation.id, 'user', message)

    const events: AgentStreamEvent[] = []
    let fullReply = ''

    await agentEngine.chat({
      userId,
      message,
      conversationId: conversation.id,
      onEvent: async (event) => {
        events.push(event)
        if (event.type === 'complete') {
          fullReply = event.content
        }
      },
    })

    if (fullReply) {
      await saveMessage(conversation.id, 'assistant', fullReply)
    }

    return {
      success: true,
      conversationId: conversation.id,
      reply: fullReply,
      events,
    }
  }

  async chatStream(params: {
    userId: number
    message: string
    conversationId?: number
    onChunk: (chunk: string) => void
  }) {
    const { userId, message, conversationId, onChunk } = params

    const conversation = await getOrCreateConversation(userId, conversationId)
    await saveMessage(conversation.id, 'user', message)

    let fullReply = ''

    await agentEngine.chat({
      userId,
      message,
      conversationId: conversation.id,
      onEvent: async (event) => {
        if (event.type === 'chunk') {
          fullReply += event.content
          onChunk(event.content)
        } else if (event.type === 'complete') {
          fullReply = event.content
        }
      },
    })

    if (fullReply) {
      await saveMessage(conversation.id, 'assistant', fullReply)
    }

    return { conversationId: conversation.id, reply: fullReply }
  }

  async recommend(city: string, budget: number, days: number) {
    const { buildTripPrompt } = await import('../prompts/trip.prompt')
    const { ChatOpenAI } = await import('@langchain/openai')
    const { HumanMessage } = await import('@langchain/core/messages')
    const { extractJson } = await import('../utils/jsonExtractor')

    if (budget < 50 || days < 1 || days > 30) {
      throw new Error('预算过低或天数不符合要求')
    }

    const modelProvider = process.env.MODEL_PROVIDER || 'DEEPSEEK'
    const apiKey = modelProvider === 'KIMI' ? process.env.KIMI_API_KEY : process.env.DEEPSEEK_API_KEY
    const baseURL = modelProvider === 'KIMI' ? process.env.KIMI_BASE_URL : process.env.DEEPSEEK_BASE_URL
    const model = modelProvider === 'KIMI' ? process.env.KIMI_MODEL : process.env.DEEPSEEK_MODEL

    const llm = new ChatOpenAI({
      configuration: { apiKey, baseURL },
      model,
      temperature: 0.7,
      streaming: false,
    })

    try {
      const response = await llm.invoke([new HumanMessage(buildTripPrompt(city, budget, days))])
      const rawContent = response.content as string
      const parsed = extractJson(rawContent) as any
      return {
        success: true,
        data: {
          city: parsed.city,
          days: parsed.days,
          totalBudget: parsed.totalBudget,
          dailyItinerary: parsed.dailyItinerary,
          budgetBreakdown: parsed.budgetBreakdown,
          tips: parsed.tips,
          warnings: parsed.warnings,
        },
      }
    } catch (error) {
      console.error('大模型调用失败:', error)
      throw new Error('大模型调用失败，请稍后重试')
    }
  }
}

export default new TripService()
