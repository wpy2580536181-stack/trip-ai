/**
 * Agent Trace API (admin)
 *
 * 后端文档：trip-server/src/controllers/trace.controller.ts
 * 路由：
 *   GET /api/admin/agent-trace/:messageId
 *   GET /api/admin/agent-trace?conversationId=N&limit=20
 *
 * 注意：request 拦截器（api/request.ts）已把 axios response.data 解包，
 * 所以 request.get<T>(...) 的 T 直接对应后端 JSON 整体（{code, data, ...}）。
 */

import request from './request'

export interface TraceStep {
  id: number
  step: number
  type: string
  name: string | null
  args: Record<string, any> | null
  output: string | null
  durationMs: number | null
  error: string | null
  createdAt: string
}

export interface TraceMessage {
  id: number
  role: string
  content: string
  metadata: any
  createdAt: string
  conversationId: number
  _count: { steps: number }
}

interface GetTraceResp {
  code: number
  data: { message: TraceMessage; steps: TraceStep[] }
}

export async function fetchAgentTrace(messageId: number): Promise<{ message: TraceMessage; steps: TraceStep[] }> {
  const res = await request.get<GetTraceResp>(`/api/admin/agent-trace/${messageId}`)
  return res.data
}

export interface TraceSummary {
  messageId: number
  preview: string
  stepCount: number
  usage: { prompt: number; completion: number; total: number; cached: number } | null
  createdAt: string
}

interface GetSummaryResp {
  code: number
  data: { summaries: TraceSummary[] }
}

export async function fetchAgentTraceSummary(
  conversationId: number,
  limit = 20,
): Promise<TraceSummary[]> {
  const res = await request.get<GetSummaryResp>(
    `/api/admin/agent-trace?conversationId=${conversationId}&limit=${limit}`,
  )
  return res.data.summaries
}
