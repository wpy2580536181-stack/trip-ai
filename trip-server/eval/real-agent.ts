/**
 * Real Agent 调用器
 *
 * 通过 HTTP 调 /api/trip/chat，收集 SSE 流，组装为 AgentOutput。
 * 多轮 fixture 自动处理：先发 history 里的 user 消息建立 conversationId，再发当前 message。
 *
 * 设计要点：
 * 1) 鉴权：用测试账号登录拿 token，token 缓存在实例
 * 2) SSE 解析：按 \n\n 切分事件，每行以 'data: ' 开头
 * 3) toolCalls：tool_start + tool_end 配对
 * 4) JSON 提取：流结束后用项目自己的 extractJson 找 JSON
 * 5) 错误处理：SSE error 事件 → AgentOutput.error
 * 6) 超时：默认 90s（agent 60s + LLM 余量 + RAG + 网络）
 */

import { extractJson } from '../src/utils/jsonExtractor'
import type { AgentOutput, Fixture, ToolCall } from './types'

interface RealAgentOptions {
  baseUrl: string         // e.g. http://127.0.0.1:3000
  username: string
  password: string
  timeoutMs?: number       // 默认 90000
  fetchImpl?: typeof fetch // 测试时可注入
  delayBetweenMs?: number  // fixture 间隔，默认 2000ms
  maxRetries?: number      // 429/5xx 重试次数，默认 3
}

interface SSEEvent {
  type: string
  content?: string
  name?: string
  data?: any
  error?: string
}

interface TokenUsage {
  prompt: number
  completion: number
  total: number
  cached?: number
}

const log = {
  info: (msg: string, extra?: any) => console.log(`[real-agent] ${msg}`, extra ?? ''),
  warn: (msg: string, extra?: any) => console.warn(`[real-agent] ${msg}`, extra ?? ''),
  error: (msg: string, extra?: any) => console.error(`[real-agent] ${msg}`, extra ?? ''),
}

export class RealAgent {
  private token: string | null = null
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number
  private readonly delayBetweenMs: number
  private readonly maxRetries: number

  constructor(private readonly options: RealAgentOptions) {
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? 90000
    this.delayBetweenMs = options.delayBetweenMs ?? 2000
    this.maxRetries = options.maxRetries ?? 3
  }

  /** fixture 之间延迟，避免触发后端 rate limit / token budget */
  async delay(): Promise<void> {
    if (this.delayBetweenMs > 0) {
      await new Promise((r) => setTimeout(r, this.delayBetweenMs))
    }
  }

  /**
   * 登录拿 JWT token
   */
  async login(): Promise<string> {
    if (this.token) return this.token

    const res = await this.fetchImpl(`${this.options.baseUrl}/api/user/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: this.options.username,
        password: this.options.password,
      }),
    })

    if (!res.ok) {
      throw new Error(`登录失败 (${res.status}): ${await res.text()}`)
    }

    const data = (await res.json()) as { data?: { token?: string } }
    if (!data.data?.token) {
      throw new Error(`登录响应无 token: ${JSON.stringify(data)}`)
    }
    this.token = data.data.token
    log.info(`登录成功，token 前缀 ${this.token.slice(0, 20)}...`)
    return this.token
  }

  /**
   * 调一次 chat 接口（含重试）
   * @param message 用户消息
   * @param conversationId 可选，沿用已有 conversation
   */
  private async chatOnce(message: string, conversationId?: number): Promise<{
    output: AgentOutput
    conversationId: number | undefined
  }> {
    let lastErr: Error | null = null
    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        return await this.chatOnceNoRetry(message, conversationId)
      } catch (e) {
        lastErr = e instanceof Error ? e : new Error(String(e))
        const msg = lastErr.message
        // 429 / 5xx / 网络错误 → 重试
        const isRetryable = /429|5\d\d|超时|aborted|network|fetch failed/i.test(msg)
        if (!isRetryable || attempt === this.maxRetries) {
          throw lastErr
        }
        const wait = 3000 * (attempt + 1)  // 3s, 6s, 9s
        log.warn(`[chat] 第 ${attempt + 1} 次失败，${wait}ms 后重试：${msg.slice(0, 100)}`)
        await new Promise((r) => setTimeout(r, wait))
      }
    }
    throw lastErr
  }

  private async chatOnceNoRetry(message: string, conversationId?: number): Promise<{
    output: AgentOutput
    conversationId: number | undefined
  }> {
    const token = await this.login()
    const start = Date.now()

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)

    let res: Response
    try {
      res = await this.fetchImpl(`${this.options.baseUrl}/api/trip/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message, conversationId }),
        signal: controller.signal,
      })
    } catch (e) {
      clearTimeout(timer)
      if ((e as any).name === 'AbortError') {
        throw new Error(`Agent 超时（${this.timeoutMs}ms）`)
      }
      throw e
    }

    if (!res.ok) {
      clearTimeout(timer)
      throw new Error(`chat 接口错误 (${res.status}): ${await res.text()}`)
    }
    if (!res.body) {
      clearTimeout(timer)
      throw new Error('chat 接口无 body')
    }

    // 解析 SSE 流
    const { text, toolCalls, error, returnedConvId, usage } = await parseSSE(res.body)
    clearTimeout(timer)
    const durationMs = Date.now() - start

    if (error) {
      return {
        output: { text, json: extractJson(text) as any, toolCalls, error, durationMs, tokens: usage },
        conversationId: returnedConvId,
      }
    }

    // 提取 JSON（agent 输出里嵌的行程 JSON）
    let json: any
    try {
      const extracted = extractJson(text)
      json = extracted
    } catch {
      json = undefined
    }

    return {
      output: { text, json, toolCalls, durationMs, tokens: usage },
      conversationId: returnedConvId,
    }
  }

  /**
   * 跑一个 fixture：
   * - 如果有 history，先逐条发 user 消息建多轮
   * - 然后发当前 message 拿最终输出
   */
  async run(fixture: Fixture): Promise<AgentOutput> {
    let conversationId: number | undefined

    // 1) 多轮准备：发 history 里的 user 消息
    if (fixture.input.history && fixture.input.history.length > 0) {
      log.info(`[${fixture.id}] 多轮准备：${fixture.input.history.length} 条 history`)

      for (const turn of fixture.input.history) {
        if (turn.role !== 'user') continue
        try {
          const result = await this.chatOnce(turn.content, conversationId)
          conversationId = result.conversationId
        } catch (e) {
          log.warn(`[${fixture.id}] history turn 失败: ${e instanceof Error ? e.message : e}（继续）`)
        }
      }
    }

    // 2) 发当前 message
    log.info(`[${fixture.id}] 跑主问题`)
    try {
      const result = await this.chatOnce(fixture.input.message, conversationId)
      return result.output
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      log.error(`[${fixture.id}] 主问题失败: ${msg}`)
      return {
        text: '',
        json: undefined,
        toolCalls: [],
        error: msg,
        durationMs: 0,
        tokens: undefined,
      }
    }
  }
}

/**
 * 解析 SSE 流
 * 格式：每条事件以 \n\n 结尾，含多行 data:
 */
async function parseSSE(body: ReadableStream<Uint8Array>): Promise<{
  text: string
  toolCalls: ToolCall[]
  error?: string
  returnedConvId?: number
  usage?: TokenUsage
}> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let text = ''
  const toolCalls: ToolCall[] = []
  let error: string | undefined
  let returnedConvId: number | undefined
  let usage: TokenUsage | undefined
  const openToolNames: string[] = []  // 维护 tool_start 到 tool_end 的栈

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // 按 \n\n 切分完整事件
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        if (!rawEvent.trim()) continue

        const event = parseOneSSEEvent(rawEvent)
        if (!event) continue

        switch (event.type) {
          case 'chunk':
            if (event.content) text += event.content
            break
          case 'tool_start':
            if (event.name) openToolNames.push(event.name)
            break
          case 'tool_end':
            const name = openToolNames.pop() || event.name || 'unknown'
            toolCalls.push({ name, timestamp: new Date().toISOString() })
            break
          case 'complete':
            if (event.data?.conversationId) {
              returnedConvId = event.data.conversationId
            }
            if ((event as any).usage) {
              usage = (event as any).usage as TokenUsage
            } else if (event.data?.usage) {
              usage = event.data.usage as TokenUsage
            }
            break
          case 'error':
            error = event.error || '未知错误'
            break
          // heartbeat: 忽略
        }
      }
    }
  } catch (e) {
    error = e instanceof Error ? e.message : String(e)
  } finally {
    reader.releaseLock()
  }

  return { text, toolCalls, error, returnedConvId, usage }
}

/** 解析一条 SSE 事件（多行 data: 拼接） */
function parseOneSSEEvent(raw: string): SSEEvent | null {
  const dataLines: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
    // 忽略 event: / id: / retry: 等字段
  }
  if (dataLines.length === 0) return null
  const dataStr = dataLines.join('\n')

  try {
    const parsed = JSON.parse(dataStr) as SSEEvent
    return parsed
  } catch {
    // 非 JSON 当 chunk
    return { type: 'chunk', content: dataStr }
  }
}
