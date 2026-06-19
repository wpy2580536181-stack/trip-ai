import { Router } from 'express'
import * as tripController from '../controllers/trip.controller'
import { authMiddleware } from '../middleware/auth'
import { createLimiter, createTokenBudgetGuard } from '../middleware/rateLimiter'
import { concurrencyGuard } from '../middleware/concurrencyGuard'
import { createIdempotencyMiddleware } from '../middleware/idempotency'

const router = Router()

const chatLimiter = createLimiter({
  windowMs: 60_000,
  max: 20,
  message: '对话请求过于频繁，请稍后再试',
})

const recommendLimiter = createLimiter({
  windowMs: 60_000,
  max: 5,
  message: '行程推荐请求过于频繁，请稍后再试',
})

const optimizeLimiter = createLimiter({
  windowMs: 60_000,
  max: 5,
  message: '行程优化请求过于频繁，请稍后再试',
})

const tokenBudgetGuard = createTokenBudgetGuard()

const idempotency = createIdempotencyMiddleware()

router.post('/recommend', authMiddleware, idempotency, recommendLimiter, tokenBudgetGuard, concurrencyGuard, tripController.recommend)
router.post('/optimize', authMiddleware, idempotency, optimizeLimiter, tokenBudgetGuard, concurrencyGuard, tripController.optimize)
router.post('/chat', authMiddleware, chatLimiter, tokenBudgetGuard, concurrencyGuard, tripController.chat)

export default router
