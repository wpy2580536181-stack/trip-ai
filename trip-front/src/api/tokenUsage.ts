import { get } from './request'

export interface TokenUsageWindow {
  current: number
  limit: number
  resetAt: number
}
export interface TokenUsageStats {
  window: TokenUsageWindow
  totalSinceStart: number
}
export interface TokenUsageLogEntry {
  userId: number | string
  endpoint: string
  tokens: number
  timestamp: number
}

export function getMyTokenStats() {
  return get('/stats/token-usage/stats', { scope: 'user' })
}

export function getGlobalTokenStats() {
  return get('/stats/token-usage/stats', { scope: 'global' })
}

export function getMyTokenLogs(limit = 50) {
  return get('/stats/token-usage/logs', { scope: 'user', limit })
}

export function getGlobalTokenLogs(limit = 50) {
  return get('/stats/token-usage/logs', { scope: 'global', limit })
}
