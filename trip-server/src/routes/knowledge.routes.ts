import { Router } from 'express'
import * as controller from '../controllers/knowledge.controller'
import { authMiddleware, roleMiddleware } from '../middleware/auth'
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
// 修复 P1-3：写操作需要 admin（roleId=1）权限
router.post('/spots', roleMiddleware(1), controller.create)
router.put('/spots/:id', roleMiddleware(1), controller.update)
router.delete('/spots/:id', roleMiddleware(1), controller.remove)

export default router
