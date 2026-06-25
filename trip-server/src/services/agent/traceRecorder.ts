/**
 * Agent Step Trace Recorder
 *
 * 把 agent 决策过程（tool 调用、step 耗时）落 DB，方便 admin 回放。
 *
 * 设计：
 * - buffer 模式：每个 step add 到内存（避免 N+1 DB 写入）
 * - flush 模式：agent 完成后一次 createMany
 * - 失败只 warn，不影响 agent 业务
 * - 同一 messageId 的 step 顺序由调用方保证
 */

import prisma from '../../config/database'
import { agentLog as log } from '../../utils/logger'

export interface StepInput {
  step: number
  type: 'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error'
  name?: string
  args?: Record<string, any>
  output?: string
  durationMs?: number
  error?: string
}

export class TraceRecorder {
  private messageId: number
  private steps: StepInput[] = []

  constructor(messageId: number) {
    this.messageId = messageId
  }

  add(step: StepInput): void {
    this.steps.push(step)
  }

  /** 写入 DB。失败只 warn，不抛错。 */
  async flush(): Promise<void> {
    if (this.steps.length === 0) return
    const data = this.steps.map((s) => ({
      messageId: this.messageId,
      step: s.step,
      type: s.type,
      name: s.name ?? null,
      args: s.args ? (s.args as any) : null,
      output: s.output ?? null,
      durationMs: s.durationMs ?? null,
      error: s.error ?? null,
    }))
    try {
      await prisma.agentStep.createMany({ data })
      log.info({ messageId: this.messageId, count: this.steps.length }, 'agent trace 落 DB')
    } catch (e) {
      log.warn({ err: e, messageId: this.messageId, count: this.steps.length }, 'agent trace 落 DB 失败')
    }
  }

  /** 测试用：拿当前已 buffer 的 steps */
  getSteps(): readonly StepInput[] {
    return this.steps
  }
}
