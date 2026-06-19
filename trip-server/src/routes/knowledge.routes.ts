import { Router } from 'express'
import * as controller from '../controllers/knowledge.controller'
import { authMiddleware } from '../middleware/auth'
import { createLimiter } from '../middleware/rateLimiter'

const router = Router()
router.use(authMiddleware)
router.use(createLimiter({
  windowMs: 60_000,
  max: 100,
  message: '知识库请求过于频繁，请稍后再试',
}))

router.get('/spots', controller.list)
router.get('/spots/:id', controller.detail)
router.post('/spots', controller.create)
router.put('/spots/:id', controller.update)
router.delete('/spots/:id', controller.remove)

export default router
