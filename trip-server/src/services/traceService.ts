/**
 * Agent Trace 查询 Service
 *
 * admin 看 agent 决策过程用
 */

import prisma from '../config/database'

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

class TraceService {
  /**
   * 查单个 message 的完整 trace（按 step 升序）
   */
  async getTraceByMessage(messageId: number): Promise<TraceStep[]> {
    const steps = await prisma.agentStep.findMany({
      where: { messageId },
      orderBy: { step: 'asc' },
      select: {
        id: true,
        step: true,
        type: true,
        name: true,
        args: true,
        output: true,
        durationMs: true,
        error: true,
        createdAt: true,
      },
    })
    return steps.map((s) => ({
      ...s,
      args: (s.args as Record<string, any> | null) ?? null,
      createdAt: s.createdAt.toISOString(),
    }))
  }

  /**
   * 查某会话最近 N 条 message 的 trace 摘要（admin dashboard 用）
   */
  async getTraceSummaryByConversation(conversationId: number, limit = 20) {
    const messages = await prisma.message.findMany({
      where: { conversationId, role: 'assistant' },
      orderBy: { createdAt: 'desc' },
      take: limit,
      select: {
        id: true,
        content: true,
        metadata: true,
        createdAt: true,
        _count: { select: { steps: true } },
      },
    })
    return messages.map((m) => {
      const meta = m.metadata as { usage?: { prompt: number; completion: number; total: number; cached: number } } | null
      return {
        messageId: m.id,
        preview: m.content.slice(0, 100),
        stepCount: m._count.steps,
        usage: meta?.usage ?? null,
        createdAt: m.createdAt.toISOString(),
      }
    })
  }

  /**
   * 单 message 的元数据 + step 数量（trace 页面头部用）
   */
  async getMessageMetadata(messageId: number) {
    const msg = await prisma.message.findUnique({
      where: { id: messageId },
      select: {
        id: true,
        role: true,
        content: true,
        metadata: true,
        createdAt: true,
        conversationId: true,
        _count: { select: { steps: true } },
      },
    })
    if (!msg) return null
    return {
      ...msg,
      createdAt: msg.createdAt.toISOString(),
    }
  }
}

export const traceService = new TraceService()
