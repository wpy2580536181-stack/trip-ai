import 'dotenv/config'
import express, { Request, Response, NextFunction } from 'express'
import cors from 'cors'
import pinoHttp from 'pino-http'
import { randomUUID } from 'crypto'
import { createLimiter } from './middleware/rateLimiter'
import { logger, httpLog } from './utils/logger'
import tripRouter from './routes/trip.routes'
import userRouter from './routes/user.routes'
import conversationRouter from './routes/conversation.routes'
import historyRouter from './routes/history.routes'
import knowledgeRouter from './routes/knowledge.routes'
import statsRouter from './routes/stats.routes'
import feedbackRouter from './routes/feedback.routes'

const app = express()
const PORT = process.env.PORT || 3000

// CORS：支持开发常用 origin（Vite 5173、demo 8080、demo 3000）
// 生产环境请设置 CORS_ORIGIN 环境变量为具体域名
const CORS_ALLOWED_ORIGINS = [
  'http://localhost:5173', // trip-front Vite dev
  'http://localhost:8080', // demo HTML 静态服务
  'http://localhost:3000', // demo HTML 直接放 trip-server public
  'http://127.0.0.1:5173',
  'http://127.0.0.1:8080',
  'http://127.0.0.1:3000',
]
const CORS_ORIGIN = process.env.CORS_ORIGIN || CORS_ALLOWED_ORIGINS.join(',')
app.use(cors({
  origin: CORS_ORIGIN.split(',').map(s => s.trim()),
  credentials: true,
}))

// pino-http：注入 req.log + 自动 access log
app.use(pinoHttp({
  logger: httpLog,
  genReqId: (req, res) => {
    const existing = req.headers['x-request-id']
    const id = (typeof existing === 'string' && existing) || randomUUID()
    res.setHeader('x-request-id', id)
    return id
  },
  customLogLevel: (_req, res, err) => {
    if (err || res.statusCode >= 500) return 'error'
    if (res.statusCode >= 400) return 'warn'
    return 'info'
  },
  customSuccessMessage: (req, res) => `${req.method} ${req.url} → ${res.statusCode}`,
  customErrorMessage: (req, res, err) => `${req.method} ${req.url} → ${res.statusCode} (${err.message})`,
  // 不记录 /api/test 健康检查
  autoLogging: {
    ignore: (req) => req.url === '/api/test',
  },
  serializers: {
    req: (req) => ({ method: req.method, url: req.url, id: req.id }),
    res: (res) => ({ statusCode: res.statusCode }),
  },
}))

app.use(express.json())

// 修复 P2-5：/api/test 仅在非生产环境暴露
if (process.env.NODE_ENV !== 'production') {
  app.get('/api/test', (req: Request, res: Response) => {
    res.json({
      code: 200,
      message: '后端服务运行正常',
      data: {
        time: new Date().toISOString(),
        env: process.env.NODE_ENV || 'development',
      },
    })
  })
}

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
app.use('/api/feedback', feedbackRouter)

app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
  req.log?.error({ err }, '未捕获异常')
  const isProduction = process.env.NODE_ENV === 'production'
  res.status(500).json({
    code: 500,
    error: isProduction ? '服务器内部错误' : err.message,
  })
})

app.listen(PORT, () => {
  logger.info({ port: PORT }, `Server running on http://localhost:${PORT}`)
})
