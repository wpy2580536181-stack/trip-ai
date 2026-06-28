import { createInterface } from 'readline'
import { logger } from '../../utils/logger'
import { AMAP_CONFIG } from '../../config/amap'
import * as amapMcpProcess from './amapMcpProcess'

export interface McpTool {
  name: string
  description: string
  inputSchema: Record<string, unknown>
}

let requestId = 0
const pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void; timer: NodeJS.Timeout }>()
let rl: ReturnType<typeof createInterface> | null = null
let initialized = false

function sendRequest(method: string, params?: unknown): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const stdin = amapMcpProcess.getStdin()
    if (!stdin || !amapMcpProcess.isAlive()) {
      return reject(new Error('MCP process not available'))
    }
    const id = ++requestId
    const request = JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n'
    const timer = setTimeout(() => {
      pending.delete(id)
      reject(new Error(`MCP request timeout: ${method}`))
    }, AMAP_CONFIG.process.timeoutMs)
    pending.set(id, { resolve, reject, timer })
    stdin.write(request)
  })
}

function handleResponse(line: string) {
  try {
    const msg = JSON.parse(line)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject, timer } = pending.get(msg.id)!
      clearTimeout(timer)
      pending.delete(msg.id)
      if (msg.error) {
        reject(new Error(msg.error.message || 'MCP error'))
      } else {
        resolve(msg.result)
      }
    }
  } catch (err) {
    logger.warn({ line, err }, '[AmapMcp] failed to parse response')
  }
}

export async function connect(): Promise<void> {
  if (initialized) return
  const stdout = amapMcpProcess.getStdout()
  if (!stdout) throw new Error('MCP process stdout not available')

  rl = createInterface({ input: stdout, crlfDelay: Infinity })
  rl.on('line', handleResponse)
  rl.on('close', () => { rl = null })

  // MCP initialize handshake
  const result = await sendRequest('initialize', {
    protocolVersion: '2024-11-05',
    capabilities: {},
    clientInfo: { name: 'trip-server', version: '1.0.0' },
  })
  initialized = true
  logger.info({ result }, '[AmapMcp] initialized')

  // 发送 initialized notification (无 response)
  const stdin = amapMcpProcess.getStdin()
  if (stdin) {
    stdin.write(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }) + '\n')
  }
}

export async function listTools(): Promise<McpTool[]> {
  const result = await sendRequest('tools/list') as { tools: McpTool[] }
  return result.tools
}

export async function callTool(name: string, args: Record<string, unknown>): Promise<string> {
  const result = await sendRequest('tools/call', { name, arguments: args }) as {
    content: Array<{ type: string; text?: string; data?: string }>
    isError?: boolean
  }
  if (result.isError) {
    throw new Error(`MCP tool ${name} returned error: ${result.content?.[0]?.text || 'unknown'}`)
  }
  return (result.content || [])
    .filter(c => c.type === 'text' && c.text)
    .map(c => c.text!)
    .join('\n')
}

export function close(): void {
  initialized = false
  if (rl) { rl.close(); rl = null }
  for (const { reject, timer } of pending.values()) {
    clearTimeout(timer)
    reject(new Error('MCP client closed'))
  }
  pending.clear()
}
