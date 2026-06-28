import { spawn, ChildProcess } from 'child_process'
import { Writable, Readable } from 'stream'
import { logger } from '../../utils/logger'
import { AMAP_CONFIG } from '../../config/amap'

let mcpProcess: ChildProcess | null = null
let healthTimer: NodeJS.Timeout | null = null
let restartAttempts = 0
let restartTimer: NodeJS.Timeout | null = null
let lastRestartMinute = 0
let restartCountThisMinute = 0
let healthCheckProbe: (() => Promise<boolean>) | null = null

export function setHealthCheckProbe(fn: () => Promise<boolean>): void {
  healthCheckProbe = fn
}

export function getStdin(): Writable | null {
  return mcpProcess?.stdin ?? null
}

export function getStdout(): Readable | null {
  return mcpProcess?.stdout ?? null
}

export function isAlive(): boolean {
  return mcpProcess !== null && !mcpProcess.killed && mcpProcess.exitCode === null
}

function resetTimers() {
  if (healthTimer) { clearInterval(healthTimer); healthTimer = null }
  if (restartTimer) { clearTimeout(restartTimer); restartTimer = null }
}

export async function start(): Promise<void> {
  if (isAlive()) return
  if (!AMAP_CONFIG.enabled) {
    logger.warn('[AmapMcp] AMAP_API_KEY not set, Amap MCP disabled')
    return
  }

  return new Promise((resolve, reject) => {
    const proc = spawn('npx', ['-y', '@amap/amap-maps-mcp-server'], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, AMAP_KEY: AMAP_CONFIG.apiKey },
    })
    mcpProcess = proc

    proc.on('spawn', () => {
      startHealthCheck()
      restartAttempts = 0
      restartCountThisMinute = 0
      logger.info('[AmapMcp] MCP server started')
      resolve()
    })

    proc.on('exit', (code, signal) => {
      logger.warn({ code, signal }, '[AmapMcp] process exited')
      mcpProcess = null
      resetTimers()
      scheduleRestart()
    })

    proc.on('error', (err) => {
      logger.error({ err }, '[AmapMcp] spawn failed')
      mcpProcess = null
      reject(err)
    })

    setTimeout(() => {
      if (!mcpProcess?.pid) {
        proc.kill()
        reject(new Error('MCP process spawn timeout'))
      }
    }, AMAP_CONFIG.process.timeoutMs)
  })
}

export function stop(): void {
  resetTimers()
  const oldProcess = mcpProcess
  if (oldProcess && !oldProcess.killed) {
    oldProcess.kill('SIGTERM')
    setTimeout(() => {
      if (oldProcess && !oldProcess.killed) oldProcess.kill('SIGKILL')
    }, 5000)
  }
  mcpProcess = null
}

function startHealthCheck() {
  healthTimer = setInterval(async () => {
    if (!isAlive()) {
      logger.warn('[AmapMcp] health check failed: process dead')
      scheduleRestart()
      return
    }
    if (healthCheckProbe) {
      try {
        const ok = await healthCheckProbe()
        if (!ok) {
          logger.warn('[AmapMcp] health check failed: probe rejected')
          scheduleRestart()
        }
      } catch (err) {
        logger.warn({ err }, '[AmapMcp] health check probe failed')
        scheduleRestart()
      }
    }
  }, AMAP_CONFIG.process.healthCheckIntervalMs)
}

function scheduleRestart() {
  const now = Date.now()
  const currentMinute = Math.floor(now / 60000)
  if (currentMinute !== lastRestartMinute) {
    restartCountThisMinute = 0
    lastRestartMinute = currentMinute
  }
  if (restartCountThisMinute >= AMAP_CONFIG.process.restartMaxPerMinute) {
    logger.error('[AmapMcp] max restarts per minute reached, giving up')
    return
  }

  const delay = Math.min(
    AMAP_CONFIG.process.restartBackoffMs * Math.pow(2, restartAttempts),
    AMAP_CONFIG.process.restartMaxBackoffMs
  )
  restartAttempts++
  restartCountThisMinute++

  restartTimer = setTimeout(() => {
    start().catch(err => logger.error({ err }, '[AmapMcp] restart failed'))
  }, delay)
  logger.info({ delay, attempt: restartAttempts }, '[AmapMcp] scheduling restart')
}
