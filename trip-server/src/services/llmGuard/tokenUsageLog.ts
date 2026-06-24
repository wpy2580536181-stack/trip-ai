const DEFAULT_MAX_LOGS = 500

export interface TokenUsageLogEntry {
  userId: string | number
  endpoint: string
  tokens: number
  /** DeepSeek prompt cache 命中的 token 数（系统提示等复用） */
  cached: number
  timestamp: number
}

export class TokenUsageLog {
  private logs: TokenUsageLogEntry[] = []
  private maxSize: number

  constructor(maxSize: number = DEFAULT_MAX_LOGS) {
    this.maxSize = maxSize
  }

  recordLog(entry: TokenUsageLogEntry): void {
    this.logs.push(entry)
    if (this.logs.length > this.maxSize) {
      this.logs.shift()
    }
  }

  getRecentLogs(opts?: { userId?: string | number; limit?: number }): TokenUsageLogEntry[] {
    const limit = opts?.limit ?? 50
    const filterUserId = opts?.userId
    let result = this.logs
    if (filterUserId !== undefined) {
      result = result.filter(l => l.userId === filterUserId)
    }
    return result.slice(-limit).reverse()
  }

  /**
   * 累计 token 统计（prompt/completion/cached）
   * 用于 dashboard 展示"整体缓存命中率"
   */
  getAggregate(opts?: { userId?: string | number }): {
    prompt: number
    completion: number
    cached: number
    callCount: number
  } {
    const filterUserId = opts?.userId
    const result = { prompt: 0, completion: 0, cached: 0, callCount: 0 }
    for (const l of this.logs) {
      if (filterUserId !== undefined && l.userId !== filterUserId) continue
      result.prompt += l.tokens // 旧 entries 只有 tokens，没有拆分
      result.cached += l.cached ?? 0
      result.callCount++
    }
    return result
  }

  clear(): void {
    this.logs = []
  }

  size(): number {
    return this.logs.length
  }
}

export const tokenUsageLog = new TokenUsageLog()
