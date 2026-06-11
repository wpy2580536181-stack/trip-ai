import { Router } from 'express'
import * as controller from '../controllers/conversation.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()
router.use(authMiddleware)

router.get('/', controller.list)
router.get('/:id', controller.detail)
router.delete('/:id', controller.remove)

export default router
