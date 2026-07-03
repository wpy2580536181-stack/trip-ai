import { agentLog as log } from '../../../utils/logger'

/** 单次请求的 Token 度量 */
export interface TokenMetrics {
  /** 请求标识 */
  requestType: 'chat' | 'recommend'
  route?: string           // 'planning' | 'general' 等路由类型
  userId: number
  conversationId?: number
  messageId?: number

  /** 请求级别聚合 */
  totalUsage: {
    prompt: number
    completion: number
    total: number
    cached: number
  }
  latencyMs: number

  /** per-node 维度（可选，有 SpanTracker 时填充） */
  perNode?: Record<string, {
    promptTokens: number
    completionTokens: number
    cachedTokens: number
    callCount: number
    durationMs: number
  }>

  /** 时间戳 */
  timestamp: number
}

/** 聚合统计结果 */
export interface TokenAggregate {
  totalPrompt: number
  totalCompletion: number
  totalCached: number
  cacheHitRate: number       // cached / prompt
  totalRequests: number
  avgLatencyMs: number
  avgTokensPerRequest: number

  /** 按请求类型 */
  perRequestType: Record<string, {
    count: number
    avgTokens: number
    avgLatencyMs: number
    cacheHitRate: number
  }>
}

const MAX_BUFFER_SIZE = 1000
const ALERT_HIGH_TOKEN_THRESHOLD = 50_000   // 单次请求超过此值告警
const ALERT_LOW_CACHE_RATE = 0.3            // 缓存命中率低于此值告警

export class TokenMonitor {
  private buffer: TokenMetrics[] = []

  /** 记录一次请求的 Token 度量 */
  record(metrics: TokenMetrics): void {
    this.buffer.push(metrics)
    // 环形缓冲区：超过上限时移除最旧的
    if (this.buffer.length > MAX_BUFFER_SIZE) {
      this.buffer.shift()
    }

    // 阈值告警
    if (metrics.totalUsage.total > ALERT_HIGH_TOKEN_THRESHOLD) {
      log.warn(
        {
          userId: metrics.userId,
          requestType: metrics.requestType,
          totalTokens: metrics.totalUsage.total,
          messageId: metrics.messageId,
        },
        `Token 消耗超阈值：单次请求 ${metrics.totalUsage.total} tokens`,
      )
    }

    if (metrics.totalUsage.prompt > 0) {
      const cacheRate = metrics.totalUsage.cached / metrics.totalUsage.prompt
      if (cacheRate < ALERT_LOW_CACHE_RATE && metrics.totalUsage.prompt > 1000) {
        log.warn(
          {
            userId: metrics.userId,
            requestType: metrics.requestType,
            cacheRate: Math.round(cacheRate * 100) / 100,
            promptTokens: metrics.totalUsage.prompt,
            cachedTokens: metrics.totalUsage.cached,
            messageId: metrics.messageId,
          },
          `Cache 命中率过低：${(cacheRate * 100).toFixed(1)}%`,
        )
      }
    }
  }

  /** 获取最近 N 条记录 */
  getRecent(limit: number = 50): TokenMetrics[] {
    return this.buffer.slice(-limit).reverse()
  }

  /** 聚合统计 */
  aggregate(opts?: { requestType?: string; userId?: number }): TokenAggregate {
    let filtered = this.buffer
    if (opts?.requestType) {
      filtered = filtered.filter(m => m.requestType === opts.requestType)
    }
    if (opts?.userId !== undefined) {
      filtered = filtered.filter(m => m.userId === opts.userId)
    }

    const result: TokenAggregate = {
      totalPrompt: 0,
      totalCompletion: 0,
      totalCached: 0,
      cacheHitRate: 0,
      totalRequests: filtered.length,
      avgLatencyMs: 0,
      avgTokensPerRequest: 0,
      perRequestType: {},
    }

    let totalLatency = 0
    for (const m of filtered) {
      result.totalPrompt += m.totalUsage.prompt
      result.totalCompletion += m.totalUsage.completion
      result.totalCached += m.totalUsage.cached
      totalLatency += m.latencyMs

      // 按请求类型聚合
      const key = m.requestType
      if (!result.perRequestType[key]) {
        result.perRequestType[key] = { count: 0, avgTokens: 0, avgLatencyMs: 0, cacheHitRate: 0 }
      }
      const bucket = result.perRequestType[key]
      bucket.count++
      bucket.avgTokens += m.totalUsage.total
      bucket.avgLatencyMs += m.latencyMs
    }

    if (filtered.length > 0) {
      result.cacheHitRate = result.totalPrompt > 0
        ? Math.round((result.totalCached / result.totalPrompt) * 100) / 100
        : 0
      result.avgLatencyMs = Math.round(totalLatency / filtered.length)
      result.avgTokensPerRequest = Math.round(
        (result.totalPrompt + result.totalCompletion) / filtered.length,
      )

      // 计算 perRequestType 的平均值
      for (const bucket of Object.values(result.perRequestType)) {
        if (bucket.count > 0) {
          bucket.avgTokens = Math.round(bucket.avgTokens / bucket.count)
          bucket.avgLatencyMs = Math.round(bucket.avgLatencyMs / bucket.count)
        }
      }
      // 计算 perRequestType 的 cacheHitRate
      for (const key of Object.keys(result.perRequestType)) {
        const typeFiltered = filtered.filter(m => m.requestType === key)
        const typePrompt = typeFiltered.reduce((s, m) => s + m.totalUsage.prompt, 0)
        const typeCached = typeFiltered.reduce((s, m) => s + m.totalUsage.cached, 0)
        result.perRequestType[key].cacheHitRate = typePrompt > 0
          ? Math.round((typeCached / typePrompt) * 100) / 100
          : 0
      }
    }

    return result
  }

  /** 当前缓冲区大小 */
  get size(): number {
    return this.buffer.length
  }

  /** 清空缓冲区 */
  clear(): void {
    this.buffer = []
  }
}

/** 全局单例 */
export const tokenMonitor = new TokenMonitor()
