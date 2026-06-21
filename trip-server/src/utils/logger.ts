import pino, { type LoggerOptions, type Logger } from 'pino'

const isProduction = process.env.NODE_ENV === 'production'
const useFile = !!process.env.LOG_FILE
const usePretty = process.env.LOG_PRETTY === 'true' || (!isProduction && !useFile)

const baseOptions: LoggerOptions = {
  level: process.env.LOG_LEVEL || (isProduction ? 'info' : 'debug'),
  timestamp: pino.stdTimeFunctions.isoTime,
  formatters: {
    level: (label) => ({ level: label }),
  },
  base: {
    service: 'trip-server',
    env: process.env.NODE_ENV || 'development',
  },
  redact: {
    paths: [
      'req.headers.authorization',
      'req.headers.cookie',
      '*.password',
      '*.token',
      '*.apiKey',
      '*.api_key',
    ],
    censor: '[REDACTED]',
  },
}

let baseLogger: Logger

try {
  if (useFile) {
    // 生产：JSON 入文件 + 可选 pretty 到 stdout
    const targets: Array<{ target: string; options?: Record<string, unknown> }> = [
      { target: 'pino/file', options: { destination: process.env.LOG_FILE, mkdir: true } },
    ]
    if (usePretty) {
      targets.push({ target: 'pino-pretty', options: { colorize: true, translateTime: 'SYS:HH:MM:ss.l' } })
    }
    baseLogger = pino(baseOptions, pino.transport({ targets }))
  } else if (usePretty) {
    // 开发：直接走 pretty
    baseLogger = pino({
      ...baseOptions,
      transport: {
        target: 'pino-pretty',
        options: { colorize: true, translateTime: 'SYS:HH:MM:ss.l', ignore: 'pid,hostname,service,env' },
      },
    })
  } else {
    // 生产无文件：JSON 到 stdout
    baseLogger = pino(baseOptions)
  }
} catch (e) {
  console.error('[Logger] 初始化失败，回退 stdout JSON:', e)
  baseLogger = pino(baseOptions)
}

export const logger = baseLogger

// 命名子 logger：每个模块导出一个 child
export const agentLog = baseLogger.child({ module: 'agent' })
export const tripLog = baseLogger.child({ module: 'trip' })
export const knowledgeLog = baseLogger.child({ module: 'knowledge' })
export const userLog = baseLogger.child({ module: 'user' })
export const authLog = baseLogger.child({ module: 'auth' })
export const summaryLog = baseLogger.child({ module: 'summary' })
export const queryRewriteLog = baseLogger.child({ module: 'queryRewrite' })
export const rerankerLog = baseLogger.child({ module: 'reranker' })
export const embeddingLog = baseLogger.child({ module: 'embedding' })
export const streamLog = baseLogger.child({ module: 'stream' })
export const llmGuardLog = baseLogger.child({ module: 'llmGuard' })
export const chromaLog = baseLogger.child({ module: 'chroma' })
export const httpLog = baseLogger.child({ module: 'http' })
