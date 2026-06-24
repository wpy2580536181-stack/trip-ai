/**
 * Feedback Service
 *
 * 用户对单条 agent 消息的在线反馈（在线评估最后一公里）
 * - 点赞 / 点踩
 * - 可选评论 + 标签
 * - 同一 user 对同一 message 只能评一次（DB unique 约束）
 * - 重复提交时 update 而非 create（避免 UX 卡顿）
 *
 * 关联：Feedback → Message → Conversation → User
 * 注意：feedback 不级联删除 Message——删除 Message 时
 *       DB 抛 FK 错是预期行为（保留反馈历史完整性）
 */

import prisma from '../config/database'
import { Prisma } from '@prisma/client'
import { feedbackLog as log } from '../utils/logger'

export interface SubmitFeedbackParams {
  userId: number
  messageId: number
  conversationId: number
  rating: 1 | -1
  comment?: string
  tags?: string[]
}

export interface FeedbackStats {
  totalCount: number
  upCount: number
  downCount: number
  satisfactionRate: number  // upCount / totalCount
  recentDownComments: Array<{
    comment: string
    tags: string[] | null
    createdAt: string
  }>
}

class FeedbackService {
  /**
   * 提交反馈（创建或更新）
   * 返回：最终记录
   */
  async submit(params: SubmitFeedbackParams) {
    const { userId, messageId, conversationId, rating, comment, tags } = params

    // 限制 tags 数量 + comment 长度（防滥用）
    const safeComment = comment?.slice(0, 500)
    const safeTags = tags && tags.length > 0 ? tags.slice(0, 5) : undefined

    try {
      const feedback = await prisma.feedback.upsert({
        where: { userId_messageId: { userId, messageId } },
        create: {
          userId,
          messageId,
          conversationId,
          rating,
          comment: safeComment,
          tags: safeTags ? (safeTags as any) : Prisma.JsonNull,
        },
        update: {
          rating,
          comment: safeComment,
          tags: safeTags ? (safeTags as any) : Prisma.JsonNull,
        },
      })
      log.info({ userId, messageId, rating }, '反馈已提交')
      return feedback
    } catch (e) {
      log.error({ err: e, params }, '提交反馈失败')
      throw e
    }
  }

  /**
   * 获取单条消息的反馈统计
   */
  async getMessageStats(messageId: number) {
    const [up, down] = await Promise.all([
      prisma.feedback.count({ where: { messageId, rating: 1 } }),
      prisma.feedback.count({ where: { messageId, rating: -1 } }),
    ])
    return {
      up,
      down,
      total: up + down,
      satisfactionRate: up + down > 0 ? up / (up + down) : null,
    }
  }

  /**
   * 列出某条消息的所有反馈（admin 调试用）
   */
  async listForMessage(messageId: number) {
    return await prisma.feedback.findMany({
      where: { messageId },
      orderBy: { createdAt: 'desc' },
      include: {
        user: { select: { id: true, username: true } },
      },
    })
  }

  /**
   * 高 token + 低满意度案例（admin dashboard 用）
   *
   * 找出负反馈（rating=-1）的 message，关联 message.metadata.usage，
   * 按 token 总数降序返回 top N。
   *
   * 用于评估"哪个 case 又慢又差"——优化 ROI 最高
   */
  async getHighTokenLowSatisfaction(sinceDays = 7, limit = 20) {
    const since = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000)
    const downs = await prisma.feedback.findMany({
      where: { createdAt: { gte: since }, rating: -1 },
      orderBy: { createdAt: 'desc' },
      take: 200, // 多取一些，filter 后再排序
      include: {
        user: { select: { id: true, username: true, nickname: true } },
      },
    })

    // 关联 message 的 metadata.usage
    const messageIds = [...new Set(downs.map((d) => d.messageId))]
    const messages = await prisma.message.findMany({
      where: { id: { in: messageIds } },
      select: { id: true, content: true, metadata: true, createdAt: true },
    })
    const msgMap = new Map(messages.map((m) => [m.id, m]))

    type Case = {
      feedbackId: number
      messageId: number
      rating: number
      comment: string | null
      tags: string[] | null
      user: { id: number; username: string; nickname: string | null }
      messagePreview: string
      usage: { prompt: number; completion: number; total: number } | null
      createdAt: string
    }

    const cases: Case[] = []
    for (const d of downs) {
      const msg = msgMap.get(d.messageId)
      if (!msg) continue
      const meta = msg.metadata as { usage?: { prompt: number; completion: number; total: number } } | null
      const usage = meta?.usage
      cases.push({
        feedbackId: d.id,
        messageId: d.messageId,
        rating: d.rating,
        comment: d.comment,
        tags: Array.isArray(d.tags) ? (d.tags as string[]) : null,
        user: { id: d.user.id, username: d.user.username, nickname: d.user.nickname },
        messagePreview: msg.content.slice(0, 200),
        usage: usage || null,
        createdAt: d.createdAt.toISOString(),
      })
    }

    // 按 token 总数降序，无 usage 的排最后
    cases.sort((a, b) => (b.usage?.total ?? -1) - (a.usage?.total ?? -1))
    return cases.slice(0, limit)
  }

  /**
   * 全局统计（admin dashboard 用）
   */
  async getGlobalStats(sinceDays = 7): Promise<FeedbackStats> {
    const since = new Date(Date.now() - sinceDays * 24 * 60 * 60 * 1000)

    const [total, up, down, recentDown] = await Promise.all([
      prisma.feedback.count({ where: { createdAt: { gte: since } } }),
      prisma.feedback.count({ where: { createdAt: { gte: since }, rating: 1 } }),
      prisma.feedback.count({ where: { createdAt: { gte: since }, rating: -1 } }),
      prisma.feedback.findMany({
        where: { createdAt: { gte: since }, rating: -1, comment: { not: null } },
        orderBy: { createdAt: 'desc' },
        take: 20,
        select: { comment: true, tags: true, createdAt: true },
      }),
    ])

    return {
      totalCount: total,
      upCount: up,
      downCount: down,
      satisfactionRate: total > 0 ? up / total : 0,
      recentDownComments: recentDown.map((f) => ({
        comment: f.comment!,
        tags: Array.isArray(f.tags) ? (f.tags as string[]) : null,
        createdAt: f.createdAt.toISOString(),
      })),
    }
  }
}

export const feedbackService = new FeedbackService()
