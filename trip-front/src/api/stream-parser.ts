/**
 * SSE 解析 + 重试退避（纯函数，无副作用）
 *
 * 设计：
 * - parseSSEEvent: 单条 SSE 事件字符串 → StreamEvent
 * - SSEParser: 累加式，处理跨 chunk 边界
 * - getBackoffMs: 指数退避（封顶 16s）
 *
 * SSE 协议字段（部分）：
 *   data: <json>     ← 必需，业务数据
 *   id: <seq>        ← 客户端用作 Last-Event-ID
 *   event: <name>    ← 事件名（end / error / 默认 message）
 *   :comment         ← 注释，跳过
 *   空行             ← 事件结束分隔
 */

export interface StreamEvent {
  type: 'chunk' | 'complete' | 'error' | 'tool_start' | 'tool_end' | 'heartbeat'
  name?: string
  content?: string
  data?: unknown
  /** SSE id 字段（数字），undefined 表示该事件没带 id */
  id?: number
  /** event: end 识别 */
  isEnd?: boolean
}

/**
 * 解析一条完整 SSE 事件
 * 入参是去掉事件间隔 \n\n 后的字符串（可能含多行）
 * 返回 null 表示空 / 注释 / 解析失败
 */
export function parseSSEEvent(raw: string): StreamEvent | null {
  if (!raw || !raw.trim()) return null

  let id: number | undefined
  const dataLines: string[] = []
  let eventName: string | undefined

  for (const line of raw.split('\n')) {
    if (!line) continue
    if (line.startsWith(':')) continue // SSE 注释

    const colonIdx = line.indexOf(':')
    if (colonIdx === -1) continue

    const field = line.slice(0, colonIdx)
    // value 去掉前导空格（SSE 规范）
    const value = colonIdx + 1 < line.length ? line.slice(colonIdx + 1).replace(/^ /, '') : ''

    if (field === 'data') {
      dataLines.push(value)
    } else if (field === 'id') {
      const n = Number(value)
      if (!Number.isNaN(n)) id = n
    } else if (field === 'event') {
      eventName = value
    }
    // 其他字段（retry: 等）暂不处理
  }

  if (dataLines.length === 0 && !eventName) return null

  // event: end 特殊处理（sentinel）
  if (eventName === 'end') {
    return { type: 'complete', isEnd: true, id }
  }

  const dataStr = dataLines.join('\n')
  let json: any
  try {
    json = JSON.parse(dataStr)
  } catch {
    return null
  }

  return {
    type: json.type,
    name: json.name,
    content: json.content,
    data: json.data,
    id,
    isEnd: eventName === 'end',
  }
}

/**
 * 累加式 SSE 解析器（处理 chunk 边界切分）
 */
export class SSEParser {
  private buffer = ''

  /**
   * 喂入一段 chunk 文本
   * 返回本 chunk 解析出的所有完整事件
   * 残留的不完整事件留在 buffer 里，等下个 chunk
   */
  feed(chunk: string): StreamEvent[] {
    this.buffer += chunk
    const events: StreamEvent[] = []

    // 按 \n\n 切分事件
    let sepIdx: number
    while ((sepIdx = this.buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = this.buffer.slice(0, sepIdx)
      this.buffer = this.buffer.slice(sepIdx + 2)
      const ev = parseSSEEvent(rawEvent)
      if (ev) events.push(ev)
    }

    return events
  }

  /** 清空 buffer（重置） */
  reset(): void {
    this.buffer = ''
  }

  /** 取得残留 buffer 内容（debug 用） */
  getPending(): string {
    return this.buffer
  }
}

/**
 * 指数退避（1s → 2s → 4s → 8s → 16s 封顶）
 * attempt 从 1 开始
 */
export function getBackoffMs(attempt: number): number {
  if (attempt < 1) return 1000
  const base = 1000
  const cap = 16000
  return Math.min(base * 2 ** (attempt - 1), cap)
}
