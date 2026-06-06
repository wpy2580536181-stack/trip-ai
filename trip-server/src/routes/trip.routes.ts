import { Router } from 'express'
import * as tripController from '../controllers/trip.controller'

const router = Router()

router.post('/recommend', tripController.recommend)
router.post('/chat', tripController.chat)

export default router
