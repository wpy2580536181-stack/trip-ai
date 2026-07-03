import 'dotenv/config'
import os from 'os'
import cluster from 'cluster'
import express, { Request, Response, NextFunction } from 'express'
import pinoHttp from 'pino-http'
import { randomUUID } from 'crypto'
import { createLimiter } from './middleware/rateLimiter'
import { logger, httpLog } from './utils/logger'
import { alertScheduler } from './services/alert/alertScheduler'
import tripRouter from './routes/trip.routes'
import userRouter from './routes/user.routes'
import conversationRouter from './routes/conversation.routes'
import historyRouter from './routes/history.routes'
import knowledgeRouter from './routes/knowledge.routes'
import statsRouter from './routes/stats.routes'
import feedbackRouter from './routes/feedback.routes'
import traceRouter from './routes/trace.routes'
import mcpRouter from './routes/mcp.routes'
import * as amapMcpProcess from './services/mcp/amapMcpProcess'
import * as amapMcpClient from './services/mcp/amapMcpClient'
import { ensureAmapTools } from './services/agent/agentEngine'

const PORT = process.env.PORT || 3000
const clusterEnabled = process.env.CLUSTER_ENABLED !== '0'
const workerCount = Math.min(
  Number(process.env.CLUSTER_WORKERS) || os.cpus().length,
  8,
)

if (clusterEnabled && cluster.isPrimary) {
  // ─── Primary 进程：只负责 Fork Worker ───
  logger.info({ workers: workerCount }, `Primary ${process.pid} starting cluster`)

  for (let i = 0; i < workerCount; i++) {
    cluster.fork()
  }

  cluster.on('exit', (worker, code, signal) => {
    logger.warn({ pid: worker.process.pid, code, signal }, 'Worker exited, restarting')
    cluster.fork()
  })

  process.on('SIGTERM', () => {
    logger.info('Primary received SIGTERM, killing workers')
    for (const id in cluster.workers) {
      cluster.workers[id]?.kill()
    }
    process.exit(0)
  })

  process.on('SIGINT', () => {
    logger.info('Primary received SIGINT, killing workers')
    for (const id in cluster.workers) {
      cluster.workers[id]?.kill()
    }
    process.exit(0)
  })
} else {
  // ─── Worker 进程：启动 Express ───
  startWorker()
}

function startWorker() {
  const app = express()

  // CORS：支持开发常用 origin + file:// 双击打开 demo HTML
  // 自实现：处理 file:// origin（'null'）特殊场景
  // 'null' origin + Access-Control-Allow-Credentials: true 浏览器会拒绝
  // demo 用 Authorization: Bearer 头（不是 cookie），不需要 credentials
  //
  // CORS 配置策略：
  // - CORS_ORIGIN 环境变量 + 默认 demo origin 合并（merge）
  // - 生产部署设 CORS_DEMO=0 可禁用 demo 默认 origin
  const CORS_DEMO_ORIGINS = [
    'http://localhost:5173', // trip-front Vite dev
    'http://localhost:8080', // demo HTML 静态服务
    'http://localhost:3000', // demo HTML 直接放 trip-server public
    'http://127.0.0.1:5173',
    'http://127.0.0.1:8080',
    'http://127.0.0.1:3000',
    'null', // file:// 双击打开 demo
  ]
  const CORS_DEMO = process.env.CORS_DEMO !== '0'
  const demoOrigins = CORS_DEMO ? CORS_DEMO_ORIGINS : []
  const envOrigins = (process.env.CORS_ORIGIN || '').split(',').map(s => s.trim()).filter(Boolean)
  const allowedOrigins = Array.from(new Set([...envOrigins, ...demoOrigins]))

  app.use((req, res, next) => {
    const origin = req.headers.origin
    if (!origin) return next()
    if (!allowedOrigins.includes(origin)) {
      return res.status(403).json({ error: `Origin ${origin} not allowed` })
    }
    res.setHeader('Access-Control-Allow-Origin', origin)
    res.setHeader('Vary', 'Origin')
    if (origin !== 'null') {
      res.setHeader('Access-Control-Allow-Credentials', 'true')
    }
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS,PATCH')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Stream-Id,Last-Event-ID,x-request-id')
    res.setHeader('Access-Control-Max-Age', '86400')
    if (req.method === 'OPTIONS') {
      return res.status(204).end()
    }
    next()
  })

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
    autoLogging: {
      ignore: (req) => req.url === '/api/test',
    },
    serializers: {
      req: (req) => ({ method: req.method, url: req.url, id: req.id }),
      res: (res) => ({ statusCode: res.statusCode }),
    },
  }))

  app.use(express.json())

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

  // 健康检查端点（负载均衡器用）
  // 不检查数据库/Redis，只检查服务是否存活
  app.get('/health', (_req: Request, res: Response) => {
    res.status(200).send('OK')
  })

  // 详细健康检查端点（监控用）
  // 只检查 MCP 进程健康状态（数据库/Redis 检查会影响性能）
  app.get('/health/detail', async (_req: Request, res: Response) => {
    const status: any = {
      status: 'ok',
      timestamp: new Date().toISOString(),
      pid: process.pid,
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      checks: {},
    }

    // 检查 MCP 进程
    try {
      const { isAlive } = await import('./services/mcp/amapMcpProcess')
      status.checks.mcp = {
        status: isAlive() ? 'ok' : 'error',
      }
    } catch (err: any) {
      status.checks.mcp = { status: 'error', message: err.message }
    }

    const httpStatus = status.status === 'ok' ? 200 : 503
    res.status(httpStatus).json(status)
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
  app.use('/api/feedback', feedbackRouter)
  app.use('/api/admin/agent-trace', traceRouter)
  app.use('/api/admin', mcpRouter)

  app.use((err: Error, req: Request, res: Response, _next: NextFunction) => {
    req.log?.error({ err }, '未捕获异常')
    const isProduction = process.env.NODE_ENV === 'production'
    res.status(500).json({
      code: 500,
      error: isProduction ? '服务器内部错误' : err.message,
    })
  })

  const server = app.listen(PORT, () => {
    logger.info({ pid: process.pid, port: PORT }, `Worker ${process.pid} started on http://localhost:${PORT}`)

    if (process.env.ALERT_ENABLED === 'true') {
      alertScheduler.start()
    }
  })

  const shutdown = (signal: string) => {
    logger.info({ signal, pid: process.pid }, 'Worker received shutdown signal')
    alertScheduler.stop()
    amapMcpClient.close()
    amapMcpProcess.stop()
    server.close(() => {
      logger.info({ pid: process.pid }, 'HTTP server closed')
      process.exit(0)
    })
  }

  async function initMcp(): Promise<void> {
    await amapMcpProcess.start()
    if (amapMcpProcess.isAlive()) {
      await amapMcpClient.connect()
      amapMcpProcess.setHealthCheckProbe(async () => {
        const tools = await amapMcpClient.listTools()
        return tools.length > 0
      })
      await ensureAmapTools()
    }
  }

  initMcp().catch(err => {
    logger.warn({ err }, '[App] Amap MCP init failed, continuing without it')
  })

  process.on('SIGTERM', () => shutdown('SIGTERM'))
  process.on('SIGINT', () => shutdown('SIGINT'))
}
