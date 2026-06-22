/**
 * Feedback Controller
 *
 * 路由：
 * POST   /api/feedback              提交反馈（user）
 * GET    /api/feedback/message/:id  查某消息的统计（user）
 * GET    /api/feedback/stats        全局统计（admin only）
 * GET    /api/feedback/list/:msgId  列出某消息所有反馈（admin only）
 */

import { Request, Response } from 'express'
import { feedbackService } from '../services/feedbackService'
import { feedbackLog as log } from '../utils/logger'

export const submit = async (req: Request, res: Response) => {
  try {
    if (!req.user) {
      return res.status(401).json({ code: 401, error: '未登录' })
    }
    const { messageId, conversationId, rating, comment, tags } = req.body as {
      messageId?: number
      conversationId?: number
      rating?: number
      comment?: string
      tags?: string[]
    }

    if (!messageId || !conversationId) {
      return res.status(400).json({ code: 400, error: 'messageId 和 conversationId 必填' })
    }
    if (rating !== 1 && rating !== -1) {
      return res.status(400).json({ code: 400, error: 'rating 必须是 1（赞）或 -1（踩）' })
    }

    // 验证 message 存在 + 属于该 user（防 IDOR 漏洞）
    const message = await require('../config/database').default.message.findUnique({
      where: { id: messageId },
      include: { conversation: { select: { userId: true } } },
    })
    if (!message) {
      return res.status(404).json({ code: 404, error: '消息不存在' })
    }
    if (message.role !== 'assistant') {
      return res.status(400).json({ code: 400, error: '只能对 agent 回复评分' })
    }
    if (message.conversation.userId !== req.user.userId) {
      return res.status(403).json({ code: 403, error: '无权操作其他用户的反馈' })
    }

    const result = await feedbackService.submit({
      userId: req.user.userId,
      messageId,
      conversationId,
      rating,
      comment,
      tags,
    })

    res.json({ code: 200, message: '反馈已记录', data: { id: result.id, rating: result.rating } })
  } catch (e) {
    log.error({ err: e }, 'submit feedback failed')
    res.status(500).json({ code: 500, error: '提交失败' })
  }
}

export const getMessageStats = async (req: Request, res: Response) => {
  try {
    const messageId = Number(req.params.id)
    if (!messageId || isNaN(messageId)) {
      return res.status(400).json({ code: 400, error: 'messageId 无效' })
    }
    const stats = await feedbackService.getMessageStats(messageId)
    res.json({ code: 200, data: stats })
  } catch (e) {
    log.error({ err: e }, 'get message stats failed')
    res.status(500).json({ code: 500, error: '查询失败' })
  }
}

export const getGlobalStats = async (req: Request, res: Response) => {
  try {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '仅管理员可访问' })
    }
    const days = Number(req.query.days) || 7
    const stats = await feedbackService.getGlobalStats(Math.min(Math.max(days, 1), 90))
    res.json({ code: 200, data: stats })
  } catch (e) {
    log.error({ err: e }, 'get global stats failed')
    res.status(500).json({ code: 500, error: '查询失败' })
  }
}

export const listForMessage = async (req: Request, res: Response) => {
  try {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '仅管理员可访问' })
    }
    const messageId = Number(req.params.msgId)
    if (!messageId || isNaN(messageId)) {
      return res.status(400).json({ code: 400, error: 'messageId 无效' })
    }
    const list = await feedbackService.listForMessage(messageId)
    res.json({ code: 200, data: list })
  } catch (e) {
    log.error({ err: e }, 'list feedback failed')
    res.status(500).json({ code: 500, error: '查询失败' })
  }
}
