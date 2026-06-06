import { Router } from 'express'
import rateLimit from 'express-rate-limit'
import { authMiddleware } from '../middleware/auth'
import * as userController from '../controllers/user.controller'

const router = Router()

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  message: { code: 429, error: '请求过于频繁，请稍后再试' },
  standardHeaders: true,
  legacyHeaders: false,
})

router.post('/register', authLimiter, userController.register)
router.post('/login', authLimiter, userController.login)
router.post('/forgot-password', authLimiter, userController.forgotPassword)
router.post('/reset-password', authLimiter, userController.resetPassword)
router.get('/info', authMiddleware, userController.getInfo)
router.put('/info', authMiddleware, userController.updateInfo)
router.put('/password', authMiddleware, userController.changePassword)

export default router
