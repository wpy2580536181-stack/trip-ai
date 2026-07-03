import { Semaphore } from './semaphore'

const ONE_MINUTE_MS = 60_000
const ONE_HOUR_MS = 3_600_000

export interface TokenBudgetConfig {
  userTokenLimit?: number
  globalTokenLimit?: number
  userWindowMs?: number
  globalWindowMs?: number
}

interface BudgetEntry {
  total: number
  resetAt: number
}

export class TokenBudgetManager {
  private userData = new Map<string | number, BudgetEntry>()
  private globalData: BudgetEntry = { total: 0, resetAt: 0 }
  private globalTotalSinceStart = 0
  private userTotalSinceStart = new Map<string | number, number>()
  private cleanupTimer: ReturnType<typeof setInterval>

  readonly userLimit: number
  readonly globalLimit: number
  readonly userWindowMs: number
  readonly globalWindowMs: number

  constructor(config?: TokenBudgetConfig) {
    this.userLimit = config?.userTokenLimit ?? (Number(process.env.USER_TOKEN_LIMIT) || 50_000)
    this.globalLimit = config?.globalTokenLimit ?? (Number(process.env.GLOBAL_TOKEN_LIMIT) || 200_000)
    this.userWindowMs = config?.userWindowMs ?? (Number(process.env.USER_TOKEN_WINDOW_MS) || ONE_HOUR_MS)
    this.globalWindowMs = config?.globalWindowMs ?? (Number(process.env.GLOBAL_TOKEN_WINDOW_MS) || ONE_MINUTE_MS)
    this.cleanupTimer = setInterval(() => this.cleanup(), ONE_MINUTE_MS)
    if (this.cleanupTimer.unref) this.cleanupTimer.unref()
  }

  checkUserBudget(userId: string | number): { allowed: boolean; current: number; limit: number; resetAt: number } {
    const now = Date.now()
    const entry = this.userData.get(userId)
    if (!entry || now >= entry.resetAt) {
      return { allowed: true, current: 0, limit: this.userLimit, resetAt: now + this.userWindowMs }
    }
    return {
      allowed: entry.total < this.userLimit,
      current: entry.total,
      limit: this.userLimit,
      resetAt: entry.resetAt,
    }
  }

  checkGlobalBudget(): { allowed: boolean; current: number; limit: number; resetAt: number } {
    const now = Date.now()
    if (now >= this.globalData.resetAt) {
      return { allowed: true, current: 0, limit: this.globalLimit, resetAt: now + this.globalWindowMs }
    }
    return {
      allowed: this.globalData.total < this.globalLimit,
      current: this.globalData.total,
      limit: this.globalLimit,
      resetAt: this.globalData.resetAt,
    }
  }

  async recordUserUsage(userId: string | number, tokens: number): Promise<void> {
    if (tokens <= 0) return
    const now = Date.now()
    let entry = this.userData.get(userId)
    if (!entry || now >= entry.resetAt) {
      entry = { total: tokens, resetAt: now + this.userWindowMs }
      this.userData.set(userId, entry)
    } else {
      entry.total += tokens
    }
    this.userTotalSinceStart.set(userId, (this.userTotalSinceStart.get(userId) ?? 0) + tokens)
  }

  async recordGlobalUsage(tokens: number): Promise<void> {
    if (tokens <= 0) return
    const now = Date.now()
    if (now >= this.globalData.resetAt) {
      this.globalData = { total: tokens, resetAt: now + this.globalWindowMs }
    } else {
      this.globalData.total += tokens
    }
    this.globalTotalSinceStart += tokens
  }

  getGlobalStats(): { window: { current: number; limit: number; resetAt: number }; totalSinceStart: number } {
    const now = Date.now()
    let current: number
    let resetAt: number
    if (now >= this.globalData.resetAt) {
      current = 0
      resetAt = now + this.globalWindowMs
    } else {
      current = this.globalData.total
      resetAt = this.globalData.resetAt
    }
    return {
      window: { current, limit: this.globalLimit, resetAt },
      totalSinceStart: this.globalTotalSinceStart,
    }
  }

  getUserStats(userId: string | number): { window: { current: number; limit: number; resetAt: number }; totalSinceStart: number } {
    const now = Date.now()
    const entry = this.userData.get(userId)
    let current: number
    let resetAt: number
    if (!entry || now >= entry.resetAt) {
      current = 0
      resetAt = now + this.userWindowMs
    } else {
      current = entry.total
      resetAt = entry.resetAt
    }
    return {
      window: { current, limit: this.userLimit, resetAt },
      totalSinceStart: this.userTotalSinceStart.get(userId) ?? 0,
    }
  }

  shutdown(): void {
    clearInterval(this.cleanupTimer)
    this.userData.clear()
    this.globalData = { total: 0, resetAt: 0 }
    this.globalTotalSinceStart = 0
    this.userTotalSinceStart.clear()
  }

  private cleanup(): void {
    const now = Date.now()
    for (const [key, entry] of this.userData) {
      if (now >= entry.resetAt) this.userData.delete(key)
    }
  }
}

export const tokenBudget = new TokenBudgetManager()
