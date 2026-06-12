import agentEngine from './agent/agentEngine'
import { getOrCreateConversation, saveMessage } from './conversationService'
import { TripContentSchema } from '../types/agent'
import { createLLM } from '../config/llm'
import { HumanMessage } from '@langchain/core/messages'
import { buildTripPrompt } from '../prompts/trip.prompt'
import { extractJson } from '../utils/jsonExtractor'
import prisma from '../config/database'

const ASSISTANT_PERSIST_FLUSH_INTERVAL_MS = 3000

export interface ChatStreamCallbacks {
  onChunk: (chunk: string) => void
  onToolStart?: (name: string) => void
  onToolEnd?: (name: string) => void
  isClientConnected?: () => boolean
}

class TripService {
  async chatStream(params: {
    userId: number
    message: string
    conversationId?: number
    callbacks: ChatStreamCallbacks
  }) {
    const { userId, message, conversationId, callbacks } = params
    const { onChunk, onToolStart, onToolEnd, isClientConnected } = callbacks

    const conversation = await getOrCreateConversation(userId, conversationId)
    await saveMessage(conversation.id, 'user', message)

    let fullReply = ''
    let lastPersistAt = Date.now()
    let persisted = false

    const tryPersist = async (force = false) => {
      if (persisted) return
      if (!force && Date.now() - lastPersistAt < ASSISTANT_PERSIST_FLUSH_INTERVAL_MS) return
      if (!fullReply) return
      lastPersistAt = Date.now()
      try {
        await prisma.message.create({
          data: { conversationId: conversation.id, role: 'assistant', content: fullReply },
        })
      } catch (e) {
        console.error('[TripService] 增量持久化失败:', e)
      }
    }

    try {
      await agentEngine.chat({
        userId,
        message,
        conversationId: conversation.id,
        onEvent: async (event) => {
          if (event.type === 'chunk') {
            fullReply += event.content
            onChunk(event.content)
            await tryPersist(false)
          } else if (event.type === 'tool_start') {
            onToolStart?.(event.name)
          } else if (event.type === 'tool_end') {
            onToolEnd?.(event.name)
          } else if (event.type === 'complete') {
            fullReply = event.content
            persisted = true
            await tryPersist(true)
          } else if (event.type === 'error') {
            await tryPersist(true)
          }
        },
      })
    } catch (e) {
      if (isClientConnected && !isClientConnected()) {
        console.warn('[TripService] 客户端已断开，强制持久化当前回复')
        await tryPersist(true)
      }
      throw e
    }

    return { conversationId: conversation.id, reply: fullReply }
  }

  async recommend(city: string, budget: number, days: number) {
    if (budget < 50 || days < 1 || days > 30) {
      throw new Error('预算过低或天数不符合要求')
    }

    const llm = createLLM({ streaming: false })

    try {
      const response = await llm.invoke([new HumanMessage(buildTripPrompt(city, budget, days))])
      const rawContent = response.content as string
      const parsed = TripContentSchema.parse(extractJson(rawContent))
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
