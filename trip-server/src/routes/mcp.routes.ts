import { Router } from 'express'
import { authMiddleware, roleMiddleware } from '../middleware/auth'
import * as mcpController from '../controllers/mcp.controller'

const router = Router()
router.use(authMiddleware)
router.get('/mcp-stats', roleMiddleware(1), mcpController.getMcpStats)

export default router
