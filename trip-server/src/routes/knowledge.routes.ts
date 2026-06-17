import { Router } from 'express'
import * as controller from '../controllers/knowledge.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()
router.use(authMiddleware)

router.get('/spots', controller.list)
router.get('/spots/:id', controller.detail)
router.post('/spots', controller.create)
router.put('/spots/:id', controller.update)
router.delete('/spots/:id', controller.remove)

export default router
