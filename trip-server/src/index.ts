import 'dotenv/config'
import express, { Request, Response, NextFunction } from 'express'
import cors from 'cors'
import { createLimiter } from './middleware/rateLimiter'
import tripRouter from './routes/trip.routes'
import userRouter from './routes/user.routes'
import conversationRouter from './routes/conversation.routes'
import historyRouter from './routes/history.routes'
import knowledgeRouter from './routes/knowledge.routes'
import statsRouter from './routes/stats.routes'

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

app.use('/api', createLimiter({
  windowMs: 60_000,
  max: 200,
  message: '系统繁忙，请稍后再试',
}))
app.use('/api/trip', tripRouter)
app.use('/api/user', userRouter)
app.use('/api/conversations', conversationRouter)
app.use('/api/history', historyRouter)
app.use('/api/knowledge', knowledgeRouter)
app.use('/api/stats', statsRouter)

app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
  console.error('[GlobalError]', err.message)
  const isProduction = process.env.NODE_ENV === 'production'
  res.status(500).json({
    code: 500,
    error: isProduction ? '服务器内部错误' : err.message,
  })
})

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`)
})
