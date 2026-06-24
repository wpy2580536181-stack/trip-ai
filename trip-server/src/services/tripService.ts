import agentEngine from './agent/agentEngine'
import { getOrCreateConversation, saveMessage, autoTitle } from './conversationService'
import { compressConversation } from './summaryService'
import { recommendCache } from './llmGuard/cache'
import prisma from '../config/database'
import { Prisma } from '@prisma/client'
import { tripLog as log } from '../utils/logger'
import type { TokenUsage } from '../types/agent'

const ASSISTANT_PERSIST_FLUSH_INTERVAL_MS = 3000

export interface ChatStreamCallbacks {
  onChunk: (chunk: string) => void
  onToolStart?: (name: string) => void
  onToolEnd?: (name: string) => void
  isClientConnected?: () => boolean
  /** complete event 携带的 LLM token usage（per-request 累计） */
  onUsage?: (usage: TokenUsage) => void
}

class TripService {
  async chatStream(params: {
    userId: number
    message: string
    conversationId?: number
    callbacks: ChatStreamCallbacks
    signal?: AbortSignal
  }) {
    const { userId, message, conversationId, callbacks, signal } = params
    const { onChunk, onToolStart, onToolEnd, isClientConnected, onUsage } = callbacks

    const conversation = await getOrCreateConversation(userId, conversationId)
    if (!conversation.title || conversation.title === '新对话') {
      await autoTitle(conversation.id, message)
    }
    await saveMessage(conversation.id, 'user', message)

    let fullReply = ''
    let assistantMsgId: number | null = null
    let lastPersistAt = Date.now()
    let persisted = false

    const persistAssistant = async (content: string, force = false, usage?: TokenUsage) => {
      if (persisted) return
      if (!content) return
      const metadata: Prisma.InputJsonValue | undefined = usage
        ? { usage: usage as unknown as Prisma.InputJsonValue }
        : undefined
      if (!assistantMsgId) {
        const msg = await prisma.message.create({
          data: {
            conversationId: conversation.id,
            role: 'assistant',
            content,
            metadata,
          },
        })
        assistantMsgId = msg.id
        lastPersistAt = Date.now()
        return
      }
      if (!force && Date.now() - lastPersistAt < ASSISTANT_PERSIST_FLUSH_INTERVAL_MS) return
      lastPersistAt = Date.now()
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          await prisma.message.update({
            where: { id: assistantMsgId },
            data: {
              content,
              metadata,
            },
          })
          return
        } catch (e) {
          if (attempt === 0) {
            await new Promise(r => setTimeout(r, 200))
            continue
          }
          log.error({ err: e }, '增量持久化失败（重试已耗尽）')
        }
      }
    }

  try {
    await agentEngine.chat({
      userId,
      message,
      conversationId: conversation.id,
      signal,
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
          await persistAssistant(fullReply, true, event.usage)
          persisted = true
          // 转发 LLM token usage 给 controller（前端 SSE 透传）
          if (event.usage) onUsage?.(event.usage)
          compressConversation(conversation.id).catch(e => {
            log.error({ err: e, conversationId: conversation.id }, '摘要压缩失败')
          })
        } else if (event.type === 'error') {
          await persistAssistant(fullReply, true)
          compressConversation(conversation.id).catch(e => {
            log.error({ err: e, conversationId: conversation.id }, '摘要压缩失败')
          })
        }
      },
    })
    } catch (e) {
      if (isClientConnected && !isClientConnected()) {
        log.warn('客户端已断开，强制持久化当前回复')
        await persistAssistant(fullReply, true)
      }
      throw e
    }

    return { conversationId: conversation.id, reply: fullReply }
  }

  async recommend(city: string, budget: number, days: number, userId: number | null = null, departureCity?: string) {
    if (budget < 50 || budget > 1_000_000 || days < 1 || days > 30) {
      throw new Error('预算或天数不符合要求（预算范围 50-1,000,000，天数 1-30）')
    }

    const cacheKey = `recommend:${city}:${budget}:${days}:${departureCity ?? 'none'}`

    try {
      const recommendResult = await recommendCache.getOrCompute(cacheKey, async () => {
        const result = await agentEngine.recommend({
          userId: userId ?? 0,
          city,
          budget,
          days,
          departureCity,
          onEvent: async () => {},
        })
        return result.parsed
      })
      const parsed = recommendResult as { city: string; days: number; [key: string]: unknown }

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
        log.error({ err: e }, 'recommend persist failed')
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
      log.error({ err: error }, '行程推荐失败')
      throw new Error('行程推荐失败，请稍后重试')
    }
  }
}

export default new TripService()
