import agentEngine from './agent/agentEngine'
import { getOrCreateConversation, saveMessage, autoTitle } from './conversationService'
import { compressConversation } from './summaryService'
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
    if (!conversation.title || conversation.title === '新对话') {
      await autoTitle(conversation.id, message)
    }
    await saveMessage(conversation.id, 'user', message)

    let fullReply = ''
    let assistantMsgId: number | null = null
    let lastPersistAt = Date.now()
    let persisted = false

    const persistAssistant = async (content: string, force = false) => {
      if (persisted) return
      if (!content) return
      if (!assistantMsgId) {
        const msg = await prisma.message.create({
          data: { conversationId: conversation.id, role: 'assistant', content },
        })
        assistantMsgId = msg.id
        lastPersistAt = Date.now()
        return
      }
      if (!force && Date.now() - lastPersistAt < ASSISTANT_PERSIST_FLUSH_INTERVAL_MS) return
      lastPersistAt = Date.now()
      try {
        await prisma.message.update({
          where: { id: assistantMsgId },
          data: { content },
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
            await persistAssistant(fullReply, false)
          } else if (event.type === 'tool_start') {
            onToolStart?.(event.name)
          } else if (event.type === 'tool_end') {
            onToolEnd?.(event.name)
          } else if (event.type === 'complete') {
            fullReply = event.content
            await persistAssistant(fullReply, true)
            persisted = true
            compressConversation(conversation.id).catch(e => {
              console.error('[TripService] 摘要压缩失败:', e instanceof Error ? e.message : e)
            })
          } else if (event.type === 'error') {
            await persistAssistant(fullReply, true)
            compressConversation(conversation.id).catch(e => {
              console.error('[TripService] 摘要压缩失败:', e instanceof Error ? e.message : e)
            })
          }
        },
      })
    } catch (e) {
      if (isClientConnected && !isClientConnected()) {
        console.warn('[TripService] 客户端已断开，强制持久化当前回复')
        await persistAssistant(fullReply, true)
      }
      throw e
    }

    return { conversationId: conversation.id, reply: fullReply }
  }

  async recommend(city: string, budget: number, days: number, userId: number | null = null, departureCity?: string) {
    if (budget < 50 || days < 1 || days > 30) {
      throw new Error('预算过低或天数不符合要求')
    }

    try {
      const { parsed } = await agentEngine.recommend({
        userId: userId ?? 0,
        city,
        budget,
        days,
        departureCity,
        onEvent: async () => {},
      })

      let savedTripId: number | null = null
      try {
        const created = await prisma.trip.create({
          data: {
            userId,
            fromCity: departureCity ?? null,
            city: parsed.city,
            days: parsed.days,
            budget,
            content: parsed as any,
            status: 'completed',
          },
        })
        savedTripId = created.id
      } catch (e) {
        console.error('[TripService] recommend persist failed:', e)
      }
      return {
        success: true,
        data: {
          id: savedTripId,
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
      console.error('行程推荐失败:', error)
      throw new Error('行程推荐失败，请稍后重试')
    }
  }
}

export default new TripService()
