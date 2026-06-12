import { Router } from 'express'
import rateLimit from 'express-rate-limit'
import * as tripController from '../controllers/trip.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()

const chatLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 20,
  message: { code: 429, error: '对话请求过于频繁，请稍后再试' },
  standardHeaders: true,
  legacyHeaders: false,
})

router.post('/recommend', tripController.recommend)
router.post('/chat', authMiddleware, chatLimiter, tripController.chat)

export default router
