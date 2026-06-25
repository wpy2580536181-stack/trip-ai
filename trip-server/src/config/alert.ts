/**
 * 告警系统配置
 *
 * 环境变量：
 *   ALERT_ENABLED         bool (default: false)  —— 是否启用调度
 *   ALERT_WEBHOOK_URL     string                 —— 接收告警的 webhook URL
 *   ALERT_WEBHOOK_TYPE    feishu|slack|dingtalk|wecom (default: feishu)
 *   ALERT_THRESHOLD       0-1 (default: 0.5)     —— 满意率阈值
 *   ALERT_MIN_FEEDBACKS   int (default: 5)       —— 最小反馈数（防误报）
 *   ALERT_INTERVAL_CRON   cron expr (default: '*\/5 * * * *')
 *   ALERT_WINDOW_MINUTES  int (default: 60)      —— 查询窗口
 *   DASHBOARD_URL         string (default: 'http://localhost:5173')
 */

export type WebhookType = 'feishu' | 'slack' | 'dingtalk' | 'wecom'

export interface AlertConfig {
  enabled: boolean
  webhookUrl: string
  webhookType: WebhookType
  threshold: number
  minFeedbacks: number
  intervalCron: string
  windowMinutes: number
  dashboardUrl: string
}

export function loadAlertConfig(): AlertConfig {
  const threshold = Number(process.env.ALERT_THRESHOLD) || 0.5
  return {
    enabled: process.env.ALERT_ENABLED === 'true',
    webhookUrl: process.env.ALERT_WEBHOOK_URL || '',
    webhookType: (process.env.ALERT_WEBHOOK_TYPE as WebhookType) || 'feishu',
    threshold: Math.max(0, Math.min(1, threshold)),
    minFeedbacks: Math.max(1, parseInt(process.env.ALERT_MIN_FEEDBACKS || '5', 10)),
    intervalCron: process.env.ALERT_INTERVAL_CRON || '*/5 * * * *',
    windowMinutes: Math.max(1, parseInt(process.env.ALERT_WINDOW_MINUTES || '60', 10)),
    dashboardUrl: process.env.DASHBOARD_URL || 'http://localhost:5173',
  }
}
