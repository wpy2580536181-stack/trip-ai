/**
 * Agent Trace Controller (admin)
 *
 * 路由：
 * GET /api/admin/agent-trace/:messageId       单 message 完整 trace
 * GET /api/admin/agent-trace?conversationId   会话最近 N 条 message 摘要
 *
 * admin only（roleId === 1）
 */

import { Request, Response } from 'express'
import { traceService } from '../services/traceService'
import { logger } from '../utils/logger'

const log = logger.child({ module: 'trace' })

/**
 * admin: 单 message 完整 trace + metadata
 * GET /api/admin/agent-trace/:messageId
 */
export const getAgentTrace = async (req: Request, res: Response) => {
  try {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '仅管理员可访问' })
    }
    const messageId = Number(req.params.messageId)
    if (!messageId || isNaN(messageId)) {
      return res.status(400).json({ code: 400, error: 'messageId 必填且为数字' })
    }
    const message = await traceService.getMessageMetadata(messageId)
    if (!message) {
      return res.status(404).json({ code: 404, error: 'message 不存在' })
    }
    const steps = await traceService.getTraceByMessage(messageId)
    res.json({ code: 200, data: { message, steps } })
  } catch (e) {
    log.error({ err: e }, 'get agent trace failed')
    res.status(500).json({ code: 500, error: '查询失败' })
  }
}

/**
 * admin: 会话最近 trace 摘要
 * GET /api/admin/agent-trace?conversationId=N&limit=20
 */
export const getAgentTraceSummary = async (req: Request, res: Response) => {
  try {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '仅管理员可访问' })
    }
    const conversationId = Number(req.query.conversationId)
    const limit = Math.min(Math.max(Number(req.query.limit) || 20, 1), 100)
    if (!conversationId || isNaN(conversationId)) {
      return res.status(400).json({ code: 400, error: 'conversationId 必填且为数字' })
    }
    const summaries = await traceService.getTraceSummaryByConversation(conversationId, limit)
    res.json({ code: 200, data: { summaries } })
  } catch (e) {
    log.error({ err: e }, 'get agent trace summary failed')
    res.status(500).json({ code: 500, error: '查询失败' })
  }
}
