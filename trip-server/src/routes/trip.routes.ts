import { Router } from 'express'
import * as tripController from '../controllers/trip.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()

router.post('/recommend', tripController.recommend)
router.post('/chat', authMiddleware, tripController.chat)

export default router
