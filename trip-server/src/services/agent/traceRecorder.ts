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

import { randomUUID } from 'crypto'
import prisma from '../../config/database'
import { agentLog as log } from '../../utils/logger'
import type { TokenUsage } from '../../types/agent'

export interface StepInput {
  step: number
  type: 'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error' | 'thinking'
  name?: string
  args?: Record<string, any>
  output?: string
  durationMs?: number
  error?: string
  parentStepId?: number
  thinkingContent?: string
}

export class TraceRecorder {
  private messageId: number
  private steps: StepInput[] = []
  private parentStepMap: Map<number, number> = new Map()

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

  /** 设置 step 的父步骤关系 */
  setParentStep(stepNumber: number, parentStepNumber: number): void {
    this.parentStepMap.set(stepNumber, parentStepNumber)
  }

  /** 获取某 step 的父步骤 */
  getParentStep(stepNumber: number): number | undefined {
    return this.parentStepMap.get(stepNumber)
  }

  /** 清空父步骤映射 */
  clearParentStepMap(): void {
    this.parentStepMap.clear()
  }
}

// ─── 分层 Span 追踪 ────────────────────────────────────────────

export interface AgentSpan {
  spanId: string
  parentSpanId: string | null
  traceId: string
  messageId: number
  agentId: string // 'router' | 'research' | 'planner' | 'validate' | 'conversationalist' | 'compress' | 'orchestrator'
  agentLabel?: string
  startedAt: number
  endedAt?: number
  durationMs?: number
  status: 'running' | 'completed' | 'failed' | 'timeout'
  tokenUsage: TokenUsage
  toolCalls: {
    tool: string
    count: number
    totalDurationMs: number
    cacheHits: number
    failures: number
  }[]
  args?: Record<string, any>
  agentSequence?: number
  input?: unknown
  output?: unknown
  error?: string
  children: AgentSpan[]
}

export class SpanTracker {
  private rootSpan: AgentSpan
  private spanStack: AgentSpan[] = []
  private messageId: number
  private activeAgents: Set<string> = new Set()
  private agentSequenceCounter: number = 0
  private timerRef?: ReturnType<typeof setTimeout>

  constructor(traceId: string, messageId: number, parentSpanId?: string) {
    this.messageId = messageId
    this.rootSpan = {
      spanId: randomUUID(),
      parentSpanId: parentSpanId ?? null,
      traceId,
      messageId,
      agentId: 'orchestrator',
      agentLabel: 'Orchestrator-000',
      startedAt: Date.now(),
      status: 'running',
      tokenUsage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      toolCalls: [],
      children: [],
    }
    this.spanStack.push(this.rootSpan)
  }

  /** 开始一个 Agent 级别的 Span */
  startAgentSpan(agentId: string): void {
    const parent = this.spanStack[this.spanStack.length - 1]
    const span: AgentSpan = {
      spanId: randomUUID(),
      parentSpanId: parent.spanId,
      traceId: this.rootSpan.traceId,
      messageId: this.messageId,
      agentId,
      startedAt: Date.now(),
      status: 'running',
      tokenUsage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      toolCalls: [],
      children: [],
    }
    span.agentSequence = ++this.agentSequenceCounter
    span.agentLabel = `Agent-${String(span.agentSequence).padStart(3, '0')}`
    parent.children.push(span)
    this.spanStack.push(span)
    this.activeAgents.add(agentId)
  }

  /** 结束当前 Span */
  endAgentSpan(extra?: {
    tokenUsage?: TokenUsage
    toolCalls?: AgentSpan['toolCalls']
    error?: string
    output?: unknown
  }): void {
    const span = this.spanStack.pop()
    if (!span || span === this.rootSpan) return // 不弹出 root
    span.endedAt = Date.now()
    span.durationMs = span.endedAt - span.startedAt
    span.status = extra?.error ? 'failed' : 'completed'
    if (extra?.tokenUsage) span.tokenUsage = extra.tokenUsage
    if (extra?.toolCalls) span.toolCalls = extra.toolCalls
    if (extra?.error) span.error = extra.error
    if (extra?.output !== undefined) span.output = extra.output
    this.activeAgents.delete(span.agentId)
  }

  /** 记录工具调用到当前 Span */
  recordToolCall(
    tool: string,
    durationMs: number,
    opts?: { cacheHit?: boolean; failure?: boolean },
  ): void {
    const current = this.spanStack[this.spanStack.length - 1]
    const existing = current.toolCalls.find((tc) => tc.tool === tool)
    if (existing) {
      existing.count++
      existing.totalDurationMs += durationMs
      if (opts?.cacheHit) existing.cacheHits++
      if (opts?.failure) existing.failures++
    } else {
      current.toolCalls.push({
        tool,
        count: 1,
        totalDurationMs: durationMs,
        cacheHits: opts?.cacheHit ? 1 : 0,
        failures: opts?.failure ? 1 : 0,
      })
    }
  }

  /** 累计 Token 到当前 Span */
  addTokenUsage(usage: Partial<TokenUsage>): void {
    const current = this.spanStack[this.spanStack.length - 1]
    if (usage.prompt) current.tokenUsage.prompt += usage.prompt
    if (usage.completion) current.tokenUsage.completion += usage.completion
    if (usage.total) current.tokenUsage.total += usage.total
    if (usage.cached) current.tokenUsage.cached += usage.cached
  }

  /** 获取根 Span 的总 Token 消耗（递归聚合 leaf Span） */
  getTotalUsage(): TokenUsage {
    function sumUsage(span: AgentSpan): TokenUsage {
      if (span.children.length === 0) return span.tokenUsage
      const result: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
      for (const child of span.children) {
        const u = sumUsage(child)
        result.prompt += u.prompt
        result.completion += u.completion
        result.total += u.total
        result.cached += u.cached
      }
      return result
    }
    return sumUsage(this.rootSpan)
  }

  /** 结束根 Span */
  endRoot(error?: string): void {
    if (this.timerRef) clearTimeout(this.timerRef)
    this.rootSpan.endedAt = Date.now()
    this.rootSpan.durationMs = this.rootSpan.endedAt - this.rootSpan.startedAt
    this.rootSpan.status = error ? 'failed' : 'completed'
    if (error) this.rootSpan.error = error
  }

  /** 设置超时定时器，超时后自动标记为 failed/timeout */
  setTimeout(ms: number): void {
    this.timerRef = setTimeout(() => {
      if (this.rootSpan.status === 'running') {
        this.rootSpan.status = 'timeout'
        this.rootSpan.error = `Trace timeout after ${ms}ms`
        this.rootSpan.endedAt = Date.now()
        this.rootSpan.durationMs = this.rootSpan.endedAt - this.rootSpan.startedAt
      }
    }, ms)
  }

  /** 追加流式输出文本到指定 Span（截断前 500 字符） */
  addOutputToSpan(spanId: string, chunk: string): void {
    const span = this.findSpan(spanId)
    if (!span) return
    const existing = (span.output as string) ?? ''
    const MAX_OUTPUT = 500
    if (existing.length >= MAX_OUTPUT) return
    const remaining = MAX_OUTPUT - existing.length
    span.output = existing + chunk.slice(0, remaining)
  }

  /** 标记根 Span 为错误状态 */
  setRootError(error: string): void {
    this.rootSpan.error = error
  }

  /** 获取所有 Span 的快照（调试用） */
  getSpansSnapshot(): AgentSpan[] {
    const result: AgentSpan[] = []
    const walk = (span: AgentSpan): void => {
      result.push(span)
      for (const child of span.children) {
        walk(child)
      }
    }
    walk(this.rootSpan)
    return result
  }

  /** 获取当前活跃 Span（栈顶） */
  getCurrentSpan(): AgentSpan {
    return this.spanStack[this.spanStack.length - 1]
  }

  /** 按 spanId 查找 Span（支持 maxDepth 限制递归深度） */
  findSpan(spanId: string, maxDepth: number = Infinity): AgentSpan | null {
    const search = (s: AgentSpan, depth: number): AgentSpan | null => {
      if (s.spanId === spanId) return s
      if (depth >= maxDepth) return null
      for (const child of s.children) {
        const found = search(child, depth + 1)
        if (found) return found
      }
      return null
    }
    return search(this.rootSpan, 0)
  }

  /** 按 agentId 查找最近的 Span（从根深度优先，返回最后一个匹配） */
  findByAgentId(agentId: string): AgentSpan | null {
    let result: AgentSpan | null = null
    const search = (s: AgentSpan): void => {
      if (s.agentId === agentId) result = s
      for (const child of s.children) {
        search(child)
      }
    }
    search(this.rootSpan)
    return result
  }

  /** 合并外部 Span 树到当前 Tracker（用于子 Agent 返回后合并） */
  mergeSpan(span: AgentSpan): void {
    if (!span) return
    const current = this.spanStack[this.spanStack.length - 1]
    // 防止重复合并同一个 Span
    if (current.children.some(c => c.spanId === span.spanId)) return
    current.children.push(span)
  }

  /** 获取全局汇总 Token（委托 getTotalUsage） */
  getMergedUsage(): TokenUsage {
    return this.getTotalUsage()
  }

  /** 获取当前 Span 栈深度 */
  getSpanStackDepth(): number {
    return this.spanStack.length
  }

  /**
   * 扁平化为 StepInput[] 格式，兼容现有 TraceRecorder.flush()
   * 通过 args 字段携带 spanId/parentSpanId 层级信息
   */
  toFlatSteps(): StepInput[] {
    const steps: StepInput[] = []
    let stepCounter = 0

    const walk = (span: AgentSpan): void => {
      const stepNumber = (span.args as any)?.stepNumber ?? stepCounter++
      steps.push({
        step: stepNumber,
        type: span.error ? 'error' : 'complete',
        name: `span:${span.agentId}`,
        args: {
          spanId: span.spanId,
          parentSpanId: span.parentSpanId,
          traceId: span.traceId,
          agentSequence: span.agentSequence,
          input: span.input,
          output: span.output,
          toolCalls: span.toolCalls.length > 0 ? span.toolCalls : undefined,
        },
        durationMs: span.durationMs,
        error: span.error,
      })
      for (const child of span.children) {
        walk(child)
      }
    }

    walk(this.rootSpan)
    return steps
  }

  /** 获取当前 Agent 序号（从根 Span 中提取） */
  getAgentSequence(): number {
    return this.agentSequenceCounter
  }

  /** 获取根 Span 的标签 */
  getAgentLabel(): string {
    return this.rootSpan.agentLabel ?? `Agent-${String(this.agentSequenceCounter).padStart(3, '0')}`
  }

  /** 获取当前活跃 Agent 数量 */
  getActiveAgentCount(): number {
    return this.activeAgents.size
  }

  /** 获取当前活跃 Agent ID 列表 */
  getActiveAgentIds(): string[] {
    return [...this.activeAgents]
  }

  /** 获取所有 Token 消耗总和（递归聚合） */
  getTotalTokenUsage(): TokenUsage {
    return this.getTotalUsage()
  }

  /** 获取根 Span */
  getRootSpan(): AgentSpan {
    return this.rootSpan
  }

  /** 获取所有未结束的 Span */
  getActiveSpans(): AgentSpan[] {
    const result: AgentSpan[] = []
    const walk = (span: AgentSpan): void => {
      if (!span.endedAt) result.push(span)
      for (const child of span.children) {
        walk(child)
      }
    }
    walk(this.rootSpan)
    return result
  }

  /** 合并外部 Trace 的 Span 树到当前 Tracker */
  mergeExternalTrace(other: SpanTracker): void {
    this.mergeSpan(other.getRootSpan())
  }

  /** 获取 Span 树最大深度 */
  getTreeDepth(): number {
    const calcDepth = (span: AgentSpan): number => {
      if (span.children.length === 0) return 1
      let maxChild = 0
      for (const child of span.children) {
        maxChild = Math.max(maxChild, calcDepth(child))
      }
      return 1 + maxChild
    }
    return calcDepth(this.rootSpan)
  }

  /** 获取 Trace 摘要信息 */
  getSummary(): {
    traceId: string
    messageId: number
    agentCount: number
    totalDurationMs: number
    errorCount: number
  } {
    let agentCount = 0
    let errorCount = 0
    const walk = (span: AgentSpan): void => {
      agentCount++
      if (span.error) errorCount++
      for (const child of span.children) {
        walk(child)
      }
    }
    walk(this.rootSpan)
    return {
      traceId: this.rootSpan.traceId,
      messageId: this.messageId,
      agentCount,
      totalDurationMs: this.rootSpan.durationMs ?? 0,
      errorCount,
    }
  }

  /** 导出为可 JSON 序列化的对象（深度优先遍历 Span 树） */
  toJSON(): {
    traceId: string
    rootSpan: AgentSpan
    spans: AgentSpan[]
    summary: ReturnType<SpanTracker['getSummary']>
  } {
    return {
      traceId: this.rootSpan.traceId,
      rootSpan: this.rootSpan,
      spans: this.getSpansSnapshot(),
      summary: this.getSummary(),
    }
  }
}

// ─── Agent 指标看板 ────────────────────────────────────────────

export interface ToolMetricEntry {
  tool: string
  callCount: number
  totalDurationMs: number
  cacheHits: number
  failures: number
}

export class AgentMetricBoard {
  private metrics: Map<
    string,
    {
      tokenUsage: TokenUsage
      toolCalls: Map<string, ToolMetricEntry>
      durationMs: number
    }
  > = new Map()

  /** 记录 Agent 执行结果 */
  record(
    agentId: string,
    opts: { tokenUsage?: TokenUsage; durationMs?: number; input?: unknown; output?: unknown },
  ): void {
    if (!this.metrics.has(agentId)) {
      this.metrics.set(agentId, {
        tokenUsage: { prompt: 0, completion: 0, total: 0, cached: 0 },
        toolCalls: new Map(),
        durationMs: 0,
      })
    }
    const entry = this.metrics.get(agentId)!
    if (opts.tokenUsage) {
      entry.tokenUsage.prompt += opts.tokenUsage.prompt
      entry.tokenUsage.completion += opts.tokenUsage.completion
      entry.tokenUsage.total += opts.tokenUsage.total
      entry.tokenUsage.cached += opts.tokenUsage.cached
    }
    if (opts.durationMs) entry.durationMs += opts.durationMs
  }

  /** 记录工具调用 */
  recordTool(agentId: string, tool: string, durationMs: number, opts?: { cacheHit?: boolean; failure?: boolean }): void {
    if (!this.metrics.has(agentId)) {
      this.metrics.set(agentId, {
        tokenUsage: { prompt: 0, completion: 0, total: 0, cached: 0 },
        toolCalls: new Map(),
        durationMs: 0,
      })
    }
    const entry = this.metrics.get(agentId)!
    const existing = entry.toolCalls.get(tool)
    if (existing) {
      existing.callCount++
      existing.totalDurationMs += durationMs
      if (opts?.cacheHit) existing.cacheHits++
      if (opts?.failure) existing.failures++
    } else {
      entry.toolCalls.set(tool, {
        tool,
        callCount: 1,
        totalDurationMs: durationMs,
        cacheHits: opts?.cacheHit ? 1 : 0,
        failures: opts?.failure ? 1 : 0,
      })
    }
  }

  /** 快照为 JSON 可序列化对象 */
  snapshot(): Record<string, { tokenUsage: TokenUsage; toolCalls: ToolMetricEntry[]; durationMs: number }> {
    const result: Record<string, { tokenUsage: TokenUsage; toolCalls: ToolMetricEntry[]; durationMs: number }> = {}
    for (const [agentId, entry] of this.metrics) {
      result[agentId] = {
        tokenUsage: { ...entry.tokenUsage },
        toolCalls: [...entry.toolCalls.values()],
        durationMs: entry.durationMs,
      }
    }
    return result
  }

  /** 获取全局汇总 Token */
  getTotalUsage(): TokenUsage {
    const result: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
    for (const entry of this.metrics.values()) {
      result.prompt += entry.tokenUsage.prompt
      result.completion += entry.tokenUsage.completion
      result.total += entry.tokenUsage.total
      result.cached += entry.tokenUsage.cached
    }
    return result
  }

  /** 获取总耗时（取各 Agent durationMs 之和） */
  getTotalDurationMs(): number {
    let total = 0
    for (const entry of this.metrics.values()) {
      total += entry.durationMs
    }
    return total
  }
}

// ─── Trace 存储 ────────────────────────────────────────────────

export interface AgentTraceRecord {
  traceId: string
  rootSpan: AgentSpan
  spans: AgentSpan[]
  metrics: ReturnType<AgentMetricBoard['snapshot']>
  totalUsage: TokenUsage
  totalDurationMs: number
  agentSequence?: number
  agentLabel?: string
  input?: unknown
  output?: unknown
}

export class TraceStore {
  private traces: Map<string, AgentTraceRecord> = new Map()
  private maxTraces: number
  private ttlMs: number

  constructor(maxTraces: number = 1000, ttlMs: number = 24 * 60 * 60 * 1000) {
    this.maxTraces = maxTraces
    this.ttlMs = ttlMs
  }

  /** 检查记录是否已过期 */
  private isExpired(record: AgentTraceRecord): boolean {
    return Date.now() - record.rootSpan.startedAt > this.ttlMs
  }

  /** 从 SpanTracker + MetricBoard 创建并存储一条 Trace 记录 */
  record(tracker: SpanTracker, board: AgentMetricBoard): AgentTraceRecord {
    const record: AgentTraceRecord = {
      traceId: tracker.getRootSpan().traceId,
      rootSpan: tracker.getRootSpan(),
      spans: tracker.getSpansSnapshot(),
      metrics: board.snapshot(),
      totalUsage: board.getTotalUsage(),
      totalDurationMs: board.getTotalDurationMs(),
      agentSequence: tracker.getAgentSequence(),
      agentLabel: tracker.getRootSpan().agentLabel,
      input: tracker.getRootSpan().input,
      output: tracker.getRootSpan().output,
    }
    this.traces.set(record.traceId, record)
    // 超限时自动清理最旧的记录
    if (this.traces.size > this.maxTraces) {
      const keys = [...this.traces.keys()]
      const toRemove = keys.slice(0, keys.length - this.maxTraces)
      for (const key of toRemove) {
        this.traces.delete(key)
      }
    }
    return record
  }

  /** 按 traceId 查询 */
  get(traceId: string): AgentTraceRecord | null {
    return this.traces.get(traceId) ?? null
  }

  /** 获取全部 Trace 记录（自动过滤已过期） */
  getAll(): AgentTraceRecord[] {
    return [...this.traces.values()].filter(r => !this.isExpired(r))
  }

  /** 按 messageId 查询关联的 Trace 记录 */
  getByMessageId(messageId: number): AgentTraceRecord[] {
    return [...this.traces.values()].filter(r => r.rootSpan.messageId === messageId)
  }

  /** 删除指定 traceId 的记录 */
  delete(traceId: string): boolean {
    return this.traces.delete(traceId)
  }

  /** 清理过期记录（按 timestamp 筛选） */
  cleanup(olderThanMs: number): void {
    const cutoff = Date.now() - olderThanMs
    for (const [traceId, record] of this.traces) {
      if (record.rootSpan.startedAt < cutoff) {
        this.traces.delete(traceId)
      }
    }
  }

  /** 获取记录总数 */
  get size(): number {
    return this.traces.size
  }

  /** 获取所有未过期的活跃 Trace */
  getActiveTraces(): AgentTraceRecord[] {
    return [...this.traces.values()].filter(r => !this.isExpired(r))
  }

  /** 按 status 过滤 Trace 记录 */
  getByStatus(status: AgentSpan['status']): AgentTraceRecord[] {
    return [...this.traces.values()].filter(r => !this.isExpired(r) && r.rootSpan.status === status)
  }

  /** 获取最近 N 条 Trace 记录（按时间倒序） */
  getRecentTraces(limit: number = 10): AgentTraceRecord[] {
    return [...this.traces.values()]
      .filter(r => !this.isExpired(r))
      .sort((a, b) => b.rootSpan.startedAt - a.rootSpan.startedAt)
      .slice(0, limit)
  }

  /** 按时间范围查询 Trace 记录 */
  getTracesByTimeRange(startTime: number, endTime: number): AgentTraceRecord[] {
    return [...this.traces.values()].filter(
      r => !this.isExpired(r) && r.rootSpan.startedAt >= startTime && r.rootSpan.startedAt <= endTime,
    )
  }

  /** 获取所有 Agent 的统计信息 */
  getAgentStats(): Record<string, { callCount: number; totalDurationMs: number; successRate: number }> {
    const stats: Record<string, { callCount: number; totalDurationMs: number; successCount: number }> = {}
    for (const record of this.traces.values()) {
      if (this.isExpired(record)) continue
      for (const span of record.spans) {
        if (!stats[span.agentId]) {
          stats[span.agentId] = { callCount: 0, totalDurationMs: 0, successCount: 0 }
        }
        stats[span.agentId].callCount++
        stats[span.agentId].totalDurationMs += span.durationMs ?? 0
        if (span.status === 'completed') stats[span.agentId].successCount++
      }
    }
    const result: Record<string, { callCount: number; totalDurationMs: number; successRate: number }> = {}
    for (const [agentId, s] of Object.entries(stats)) {
      result[agentId] = {
        callCount: s.callCount,
        totalDurationMs: s.totalDurationMs,
        successRate: s.callCount > 0 ? s.successCount / s.callCount : 0,
      }
    }
    return result
  }

  /** 获取所有工具的使用统计 */
  getToolUsageStats(): Record<string, { callCount: number; avgDurationMs: number }> {
    const stats: Record<string, { callCount: number; totalDurationMs: number }> = {}
    for (const record of this.traces.values()) {
      if (this.isExpired(record)) continue
      for (const span of record.spans) {
        for (const tc of span.toolCalls) {
          if (!stats[tc.tool]) {
            stats[tc.tool] = { callCount: 0, totalDurationMs: 0 }
          }
          stats[tc.tool].callCount += tc.count
          stats[tc.tool].totalDurationMs += tc.totalDurationMs
        }
      }
    }
    const result: Record<string, { callCount: number; avgDurationMs: number }> = {}
    for (const [tool, s] of Object.entries(stats)) {
      result[tool] = {
        callCount: s.callCount,
        avgDurationMs: s.callCount > 0 ? s.totalDurationMs / s.callCount : 0,
      }
    }
    return result
  }

  /** 导出所有 Trace 为 JSON 字符串 */
  exportToJSON(): string {
    const records = [...this.traces.values()].filter(r => !this.isExpired(r))
    return JSON.stringify(records, null, 2)
  }
}
