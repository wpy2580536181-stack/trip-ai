/**
 * 告警调度器
 *
 * 用 node-cron 每 5 分钟跑一次 alert check
 * 集成到 index.ts 启动时
 *
 * tick() 单独暴露，方便测试和手动触发
 */

import cron, { type ScheduledTask } from 'node-cron'
import { loadAlertConfig } from '../../config/alert'
import { alertDetector } from './alertDetector'
import { webhookNotifier } from './webhookNotifier'
import { alertDeduplicator } from './alertDeduplicator'
import { alertLog as log } from '../../utils/logger'

class AlertScheduler {
  private task: ScheduledTask | null = null

  start(): void {
    const cfg = loadAlertConfig()
    if (!cfg.enabled) {
      log.info('告警调度未启用（ALERT_ENABLED=false）')
      return
    }
    if (!cfg.webhookUrl) {
      log.warn('ALERT_ENABLED=true 但 ALERT_WEBHOOK_URL 未配置，调度器不启动')
      return
    }
    if (!cron.validate(cfg.intervalCron)) {
      log.error({ cron: cfg.intervalCron }, 'cron 表达式非法，调度器不启动')
      return
    }

    this.task = cron.schedule(cfg.intervalCron, () => {
      this.tick().catch((e) => log.error({ err: e }, 'tick 异常'))
    })
    log.info({ cron: cfg.intervalCron, type: cfg.webhookType, threshold: cfg.threshold, minFeedbacks: cfg.minFeedbacks, windowMinutes: cfg.windowMinutes }, '告警调度已启动')
  }

  stop(): void {
    if (this.task) {
      this.task.stop()
      this.task = null
      log.info('告警调度已停止')
    }
  }

  async tick(): Promise<{ shouldAlert: boolean; sent: boolean; reason: string }> {
    const check = await alertDetector.check()
    if (!check.shouldAlert) {
      log.debug({ reason: check.reason }, '告警检查：正常，无需发送')
      return { shouldAlert: false, sent: false, reason: check.reason }
    }

    if (!(await alertDeduplicator.shouldSend())) {
      log.info({ reason: check.reason }, '告警已被去重（5min 桶内已发送）')
      return { shouldAlert: true, sent: false, reason: check.reason }
    }

    const result = await webhookNotifier.send(check)
    if (result.success) {
      await alertDeduplicator.markSent()
      log.info({ attempts: result.attempts, reason: check.reason }, '告警已发送')
      return { shouldAlert: true, sent: true, reason: check.reason }
    }
    log.error({ error: result.error, attempts: result.attempts, reason: check.reason }, '告警发送失败')
    return { shouldAlert: true, sent: false, reason: check.reason }
  }
}

export const alertScheduler = new AlertScheduler()
