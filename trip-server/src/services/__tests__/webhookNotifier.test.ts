import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockLoadAlertConfig = vi.fn()

vi.mock('../../config/alert', () => ({
  loadAlertConfig: () => mockLoadAlertConfig(),
  WebhookType: {} as any,
}))

import { webhookNotifier } from '../alert/webhookNotifier'
import type { AlertCheckResult } from '../alert/alertDetector'

const baseCheck: AlertCheckResult = {
  shouldAlert: true,
  reason: '过去 60 分钟 7 条反馈，满意率 28.6% < 50%',
  stats: {
    feedbackCount: 7,
    upCount: 2,
    downCount: 5,
    satisfactionRate: 0.286,
    recentDownComments: [
      { comment: '推荐不准', tags: ['recommend'], createdAt: '2026-06-25T15:00:00Z' },
      { comment: '太慢', tags: null, createdAt: '2026-06-25T15:01:00Z' },
    ],
  },
  threshold: 0.5,
  minFeedbacks: 5,
}

describe('WebhookNotifier - formatPayload', () => {
  beforeEach(() => {
    mockLoadAlertConfig.mockReturnValue({
      webhookUrl: 'http://test',
      webhookType: 'feishu',
      dashboardUrl: 'http://localhost:5173',
    })
  })

  it('feishu 格式', () => {
    const p = webhookNotifier.formatPayload('feishu', baseCheck, 'http://localhost:5173')
    expect(p.msg_type).toBe('interactive')
    expect(p.card.header.title.content).toContain('Feedback 满意率告警')
    expect(p.card.elements[0].text.content).toContain('28.6%')
    expect(p.card.elements[1].actions[0].url).toContain('/admin/feedback')
  })

  it('slack 格式', () => {
    const p = webhookNotifier.formatPayload('slack', baseCheck, 'http://localhost:5173')
    expect(p.text).toContain('Feedback 满意率告警')
    expect(p.blocks[0].text.text).toContain('推荐不准')
    expect(p.blocks[1].elements[0].url).toContain('/admin/feedback')
  })

  it('dingtalk 格式', () => {
    const p = webhookNotifier.formatPayload('dingtalk', baseCheck, 'http://localhost:5173')
    expect(p.msgtype).toBe('markdown')
    expect(p.markdown.text).toContain('28.6%')
    expect(p.markdown.text).toContain('推荐不准')
    expect(p.markdown.text).toContain('/admin/feedback')
  })

  it('wecom 格式', () => {
    const p = webhookNotifier.formatPayload('wecom', baseCheck, 'http://localhost:5173')
    expect(p.msgtype).toBe('markdown')
    expect(p.markdown.content).toContain('28.6%')
  })

  it('recentDownComments 为空时显示"无评论"', () => {
    const p = webhookNotifier.formatPayload(
      'feishu',
      { ...baseCheck, stats: { ...baseCheck.stats, recentDownComments: [] } },
      'http://localhost:5173',
    )
    expect(p.card.elements[0].text.content).toContain('（无评论）')
  })
})

describe('WebhookNotifier - send', () => {
  beforeEach(() => {
    mockLoadAlertConfig.mockReset()
  })

  it('webhookUrl 未配置 → success=false', async () => {
    mockLoadAlertConfig.mockReturnValue({ webhookUrl: '', webhookType: 'feishu' })
    const r = await webhookNotifier.send(baseCheck)
    expect(r.success).toBe(false)
    expect(r.error).toContain('未配置')
  })

  it('发送成功（mock fetch 200）', async () => {
    mockLoadAlertConfig.mockReturnValue({ webhookUrl: 'http://test', webhookType: 'feishu' })
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', mockFetch)
    try {
      const r = await webhookNotifier.send(baseCheck)
      expect(r.success).toBe(true)
      expect(r.attempts).toBe(1)
      expect(mockFetch).toHaveBeenCalledTimes(1)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('发送失败 retry 3 次（500 响应）', async () => {
    mockLoadAlertConfig.mockReturnValue({ webhookUrl: 'http://test', webhookType: 'feishu' })
    const mockFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    vi.stubGlobal('fetch', mockFetch)
    // 跳过实际 1s+3s+9s=13s 等待：fake timers + 手动推进
    vi.useFakeTimers()
    try {
      const promise = webhookNotifier.send(baseCheck)
      // 推进 3 次退避
      await vi.advanceTimersByTimeAsync(1000)
      await vi.advanceTimersByTimeAsync(3000)
      await vi.advanceTimersByTimeAsync(9000)
      const r = await promise
      expect(r.success).toBe(false)
      expect(r.attempts).toBe(3)
      expect(mockFetch).toHaveBeenCalledTimes(3)
    } finally {
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  })

  it('网络异常 retry 3 次后失败', async () => {
    mockLoadAlertConfig.mockReturnValue({ webhookUrl: 'http://test', webhookType: 'feishu' })
    const mockFetch = vi.fn().mockRejectedValue(new Error('network'))
    vi.stubGlobal('fetch', mockFetch)
    vi.useFakeTimers()
    try {
      const promise = webhookNotifier.send(baseCheck)
      await vi.advanceTimersByTimeAsync(1000)
      await vi.advanceTimersByTimeAsync(3000)
      await vi.advanceTimersByTimeAsync(9000)
      const r = await promise
      expect(r.success).toBe(false)
      expect(r.attempts).toBe(3)
      expect(r.error).toBe('network')
    } finally {
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  })
})
