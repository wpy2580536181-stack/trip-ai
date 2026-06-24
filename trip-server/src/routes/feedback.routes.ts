/**
 * Feedback Routes
 *
 * 路由：/api/feedback/*
 * 限流：30 次/小时/IP（防刷）
 */

import { Router } from 'express'
import * as feedbackController from '../controllers/feedback.controller'
import { authMiddleware } from '../middleware/auth'
import { createLimiter } from '../middleware/rateLimiter'

const router = Router()

// 反馈提交限流（防刷）
const feedbackLimiter = createLimiter({
  windowMs: 60 * 60 * 1000,  // 1 小时
  max: 30,
  message: '反馈提交过于频繁，请稍后再试',
})

// 用户提交反馈
router.post('/', authMiddleware, feedbackLimiter, feedbackController.submit)

// 查询某消息统计（任意登录用户）
router.get('/message/:id', authMiddleware, feedbackController.getMessageStats)

// admin 全局统计
router.get('/stats', authMiddleware, feedbackController.getGlobalStats)

// admin 列出某消息所有反馈
router.get('/list/:msgId', authMiddleware, feedbackController.listForMessage)

// admin 高 token + 低满意度案例（用于 ROI 优化）
router.get('/admin/high-token-low-satisfaction', authMiddleware, feedbackController.getHighTokenLowSatisfaction)

export default router
