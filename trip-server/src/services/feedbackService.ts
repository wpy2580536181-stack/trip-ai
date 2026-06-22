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
