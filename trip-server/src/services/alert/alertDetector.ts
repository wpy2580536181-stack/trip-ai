/**
 * 告警检测器
 *
 * 查过去 N 分钟 feedback，计算 satisfactionRate，判断是否低于阈值。
 * 阈值判断逻辑：
 *   - 反馈数 >= minFeedbacks（防样本太少误报）
 *   - satisfactionRate < threshold
 * 两个条件都满足才告警。
 */

import prisma from '../../config/database'
import { loadAlertConfig } from '../../config/alert'
import { alertLog as log } from '../../utils/logger'

export interface AlertCheckResult {
  shouldAlert: boolean
  reason: string
  stats: {
    feedbackCount: number
    upCount: number
    downCount: number
    satisfactionRate: number
    recentDownComments: Array<{ comment: string; tags: string[] | null; createdAt: string }>
  }
  threshold: number
  minFeedbacks: number
}

class AlertDetector {
  async check(): Promise<AlertCheckResult> {
    const cfg = loadAlertConfig()
    const since = new Date(Date.now() - cfg.windowMinutes * 60 * 1000)

    const [up, down, recentDown] = await Promise.all([
      prisma.feedback.count({ where: { createdAt: { gte: since }, rating: 1 } }),
      prisma.feedback.count({ where: { createdAt: { gte: since }, rating: -1 } }),
      prisma.feedback.findMany({
        where: { createdAt: { gte: since }, rating: -1, comment: { not: null } },
        orderBy: { createdAt: 'desc' },
        take: 5,
        select: { comment: true, tags: true, createdAt: true },
      }),
    ])

    const total = up + down
    const rate = total > 0 ? up / total : 0
    const shouldAlert = total >= cfg.minFeedbacks && rate < cfg.threshold

    const reason = shouldAlert
      ? `过去 ${cfg.windowMinutes} 分钟 ${total} 条反馈，满意率 ${(rate * 100).toFixed(1)}% < ${(cfg.threshold * 100).toFixed(0)}%`
      : total < cfg.minFeedbacks
        ? `样本不足：${total}/${cfg.minFeedbacks} 反馈`
        : `正常：${total} 条反馈，满意率 ${(rate * 100).toFixed(1)}%`

    log.debug({ shouldAlert, total, rate, reason }, '告警检测')

    return {
      shouldAlert,
      reason,
      stats: {
        feedbackCount: total,
        upCount: up,
        downCount: down,
        satisfactionRate: rate,
        recentDownComments: recentDown.map((f) => ({
          comment: f.comment!,
          tags: Array.isArray(f.tags) ? (f.tags as string[]) : null,
          createdAt: f.createdAt.toISOString(),
        })),
      },
      threshold: cfg.threshold,
      minFeedbacks: cfg.minFeedbacks,
    }
  }
}

export const alertDetector = new AlertDetector()
