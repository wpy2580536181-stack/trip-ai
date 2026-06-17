import { Router } from 'express'
import * as controller from '../controllers/history.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()
router.use(authMiddleware)

router.get('/trips', controller.listTrips)
router.get('/trips/:id', controller.getTrip)
router.delete('/trips/:id', controller.deleteTrip)

export default router
