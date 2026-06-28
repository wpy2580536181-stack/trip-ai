import { Router } from 'express'
import { authMiddleware } from '../middleware/auth'
import * as mcpController from '../controllers/mcp.controller'

const router = Router()
router.use(authMiddleware)
router.get('/mcp-stats', mcpController.getMcpStats)

export default router
