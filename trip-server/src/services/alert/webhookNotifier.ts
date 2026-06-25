/**
 * Webhook 通知器
 *
 * 支持 4 种 IM 格式：飞书 / Slack / 钉钉 / 企业微信
 * 失败 retry 3 次（1s/3s/9s 指数退避）
 * 失败只 warn log，不抛错
 */

import { loadAlertConfig, type WebhookType } from '../../config/alert'
import type { AlertCheckResult } from './alertDetector'
import { alertLog as log } from '../../utils/logger'

export interface SendResult {
  success: boolean
  attempts: number
  error?: string
}

class WebhookNotifier {
  async send(check: AlertCheckResult): Promise<SendResult> {
    const cfg = loadAlertConfig()
    if (!cfg.webhookUrl) {
      return { success: false, attempts: 0, error: 'webhookUrl 未配置' }
    }

    const payload = this.formatPayload(cfg.webhookType, check, cfg.dashboardUrl)
    const maxAttempts = 3

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const res = await fetch(cfg.webhookUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (res.ok) {
          log.info({ type: cfg.webhookType, attempt: attempt + 1, status: res.status }, '告警发送成功')
          return { success: true, attempts: attempt + 1 }
        }
        log.warn({ type: cfg.webhookType, attempt: attempt + 1, status: res.status }, 'webhook 返回非 200')
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        if (attempt === maxAttempts - 1) {
          log.error({ err: msg, type: cfg.webhookType, attempts: maxAttempts }, 'webhook 发送最终失败')
          return { success: false, attempts: maxAttempts, error: msg }
        }
        log.warn({ err: msg, attempt: attempt + 1 }, 'webhook 发送失败，将重试')
      }
      // 指数退避：1s, 3s, 9s
      await new Promise((r) => setTimeout(r, 1000 * Math.pow(3, attempt)))
    }
    return { success: false, attempts: maxAttempts, error: 'all retries failed' }
  }

  formatPayload(type: WebhookType, check: AlertCheckResult, dashboardUrl: string): any {
    const title = '⚠️ Feedback 满意率告警'
    const summary = check.reason
    const comments = check.stats.recentDownComments
      .map((c) => {
        const tagStr = c.tags && c.tags.length > 0 ? ` [${c.tags.join(', ')}]` : ''
        return `- ${c.comment}${tagStr}`
      })
      .join('\n')
    const link = `${dashboardUrl}/admin/feedback`

    switch (type) {
      case 'feishu':
        return {
          msg_type: 'interactive',
          card: {
            header: { title: { tag: 'plain_text', content: title } },
            elements: [
              {
                tag: 'div',
                text: {
                  tag: 'lark_md',
                  content: `**${summary}**\n\n最近差评：\n${comments || '（无评论）'}`,
                },
              },
              {
                tag: 'action',
                actions: [
                  {
                    tag: 'button',
                    text: { tag: 'plain_text', content: '查看 Dashboard' },
                    type: 'primary',
                    url: link,
                  },
                ],
              },
            ],
          },
        }
      case 'slack':
        return {
          text: title,
          blocks: [
            {
              type: 'section',
              text: { type: 'mrkdwn', text: `*${summary}*\n\n最近差评：\n${comments || '（无评论）'}` },
            },
            {
              type: 'actions',
              elements: [{ type: 'button', text: { type: 'plain_text', text: '查看 Dashboard' }, url: link }],
            },
          ],
        }
      case 'dingtalk':
        return {
          msgtype: 'markdown',
          markdown: {
            title,
            text: `**${summary}**\n\n最近差评：\n${comments || '（无评论）'}\n\n[查看 Dashboard](${link})`,
          },
        }
      case 'wecom':
        return {
          msgtype: 'markdown',
          markdown: {
            content: `**${title}**\n\n${summary}\n\n最近差评：\n${comments || '（无评论）'}`,
          },
        }
      default:
        return { text: `${title}\n${summary}\n${comments}` }
    }
  }
}

export const webhookNotifier = new WebhookNotifier()
