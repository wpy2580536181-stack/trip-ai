/**
 * Agent Trace Routes (admin)
 *
 * 路由：/api/admin/agent-trace/*
 * admin only（路由内每个 handler 自检 roleId）
 */

import { Router } from 'express'
import * as traceController from '../controllers/trace.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()

// admin: 单 message 完整 trace
router.get('/:messageId', authMiddleware, traceController.getAgentTrace)

// admin: 会话最近 trace 摘要（query: conversationId, limit）
router.get('/', authMiddleware, traceController.getAgentTraceSummary)

export default router
