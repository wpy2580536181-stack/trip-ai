import { Router } from 'express'
import { authMiddleware } from '../middleware/auth'
import * as statsController from '../controllers/stats.controller'

const router = Router()
router.use(authMiddleware)
router.get('/token-usage/stats', statsController.getTokenUsageStats)
router.get('/token-usage/logs', statsController.getTokenUsageLogs)

export default router
