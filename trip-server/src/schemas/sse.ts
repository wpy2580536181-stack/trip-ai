/**
 * SSE 事件类型定义
 *
 * 定义 SSE 流中传输的事件负载格式。
 * 与 AgentStreamEvent 对齐，但独立于 LangChain 类型。
 */

/**
 * SSE 事件负载
 *
 * 类型说明：
 * - chunk: LLM 输出的文本片段
 * - complete: Agent 执行完成，携带最终回复和 token usage
 * - error: 执行出错
 * - tool_start: 工具调用开始（如知识检索、天气查询）
 * - tool_end: 工具调用结束
 * - heartbeat: 心跳事件（每 5s 发送，保持连接）
 */
export interface SSEPayload {
  type: 'chunk' | 'complete' | 'error' | 'tool_start' | 'tool_end' | 'heartbeat'
  /** tool_start/tool_end 时的工具名称 */
  name?: string
  /** chunk 时的文本片段、complete 时的完整回复、error 时的错误信息 */
  content?: string
  /** 附加数据（如 complete 时的 conversationId、token usage） */
  data?: unknown
}

/**
 * SSE 事件（带序列号）
 *
 * Redis 存储格式，包含 seq 用于断点续传。
 */
export interface SSEEvent {
  seq: number
  type: string
  data: SSEPayload
  createdAt: number
}

/**
 * 流状态
 */
export type StreamStatus = 'active' | 'completed' | 'error'

/**
 * 流元数据
 */
export interface StreamState {
  streamId: string
  userId: string
  conversationId: string
  status: StreamStatus
  createdAt: number
  lastEventAt: number
  totalSeq: number
}
