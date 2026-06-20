import { Request, Response } from 'express'
import { tokenBudget } from '../services/llmGuard/tokenBudget'
import { tokenUsageLog } from '../services/llmGuard/tokenUsageLog'

export const getTokenUsageStats = (req: Request, res: Response): Response => {
  const scope = (req.query.scope as string) || 'user'
  if (scope === 'global') {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '权限不足' })
    }
    return res.json({ code: 200, data: tokenBudget.getGlobalStats() })
  }
  const userId = req.user?.userId ?? 0
  return res.json({ code: 200, data: tokenBudget.getUserStats(userId) })
}

export const getTokenUsageLogs = (req: Request, res: Response): Response => {
  const scope = (req.query.scope as string) || 'user'
  const limit = Math.min(Number(req.query.limit) || 50, 200)
  if (scope === 'global') {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '权限不足' })
    }
    return res.json({ code: 200, data: tokenUsageLog.getRecentLogs({ limit }) })
  }
  const userId = req.user?.userId ?? 0
  return res.json({ code: 200, data: tokenUsageLog.getRecentLogs({ userId, limit }) })
}
