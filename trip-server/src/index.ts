import 'dotenv/config'
import express, { Request, Response } from 'express'
import cors from 'cors'
import tripRouter from './routes/trip.routes'
import userRouter from './routes/user.routes'
import conversationRouter from './routes/conversation.routes'
import historyRouter from './routes/history.routes'

const app = express()
const PORT = process.env.PORT || 3000

const CORS_ORIGIN = process.env.CORS_ORIGIN || 'http://localhost:5173'
app.use(cors({
  origin: CORS_ORIGIN,
  credentials: true,
}))
app.use(express.json())

app.get('/api/test', (req: Request, res: Response) => {
  res.json({
    code: 200,
    message: '后端服务运行正常',
    data: {
      time: new Date().toISOString(),
      env: 'development',
    },
  })
})

app.use('/api/trip', tripRouter)
app.use('/api/user', userRouter)
app.use('/api/conversations', conversationRouter)
app.use('/api/history', historyRouter)

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`)
})
