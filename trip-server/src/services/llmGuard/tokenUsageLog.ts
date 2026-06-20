const DEFAULT_MAX_LOGS = 500

export interface TokenUsageLogEntry {
  userId: string | number
  endpoint: string
  tokens: number
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

  clear(): void {
    this.logs = []
  }

  size(): number {
    return this.logs.length
  }
}

export const tokenUsageLog = new TokenUsageLog()
