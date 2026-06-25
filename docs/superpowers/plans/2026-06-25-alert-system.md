# 反馈自动告警系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每 5 分钟检查一次 feedback 满意度，低于阈值时自动发飞书/Slack/钉钉/企业微信告警，让 owner 不用盯 dashboard 也能知道质量问题。

**Architecture:** alertDetector 查 1h feedback → 阈值判断 → Redis 5min 桶去重 → webhookNotifier 发 4 种 IM 格式之一 → node-cron 调度。环境变量配置，`ALERT_ENABLED` 默认 false 显式开启。

**Tech Stack:** Node.js + Prisma + ioredis（已有）+ node-cron + Vitest

---

## 文件结构

```
trip-server/
├── src/
│   ├── config/
│   │   └── alert.ts                          # NEW 配置加载
│   ├── services/
│   │   ├── alert/
│   │   │   ├── alertDetector.ts              # NEW 检测器
│   │   │   ├── webhookNotifier.ts            # NEW 发送器
│   │   │   ├── alertDeduplicator.ts          # NEW 去重
│   │   │   └── alertScheduler.ts             # NEW 调度器
│   │   └── __tests__/
│   │       ├── alertDetector.test.ts         # NEW 5 单测
│   │       └── webhookNotifier.test.ts       # NEW 8 单测
│   └── index.ts                              # 启动时 initScheduler
docs/
└── alert-system.md                           # NEW 使用文档
```

---

## Task 1: config/alert.ts 配置加载

**Files:**
- Create: `trip-server/src/config/alert.ts`

- [ ] **Step 1: 写 alert.ts**

```typescript
/**
 * 告警系统配置
 *
 * 环境变量：
 *   ALERT_ENABLED         bool (default: false)  —— 是否启用调度
 *   ALERT_WEBHOOK_URL     string                 —— 接收告警的 webhook URL
 *   ALERT_WEBHOOK_TYPE    feishu|slack|dingtalk|wecom (default: feishu)
 *   ALERT_THRESHOLD       0-1 (default: 0.5)     —— 满意率阈值
 *   ALERT_MIN_FEEDBACKS   int (default: 5)       —— 最小反馈数（防误报）
 *   ALERT_INTERVAL_CRON   cron expr (default: '*/5 * * * *')
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
    threshold: Math.max(0, Math.min(1, threshold)),  // clamp 0-1
    minFeedbacks: Math.max(1, parseInt(process.env.ALERT_MIN_FEEDBACKS || '5', 10)),
    intervalCron: process.env.ALERT_INTERVAL_CRON || '*/5 * * * *',
    windowMinutes: Math.max(1, parseInt(process.env.ALERT_WINDOW_MINUTES || '60', 10)),
    dashboardUrl: process.env.DASHBOARD_URL || 'http://localhost:5173',
  }
}
```

- [ ] **Step 2: typecheck**

```bash
cd /Users/wang/Documents/trip/trip-server && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/src/config/alert.ts
git commit -m "feat(alert): config loader with env var validation"
```

---

## Task 2: alertDetector.ts + 5 单元测试

**Files:**
- Create: `trip-server/src/services/alert/alertDetector.ts`
- Create: `trip-server/src/services/__tests__/alertDetector.test.ts`

- [ ] **Step 1: 写 alertDetector.ts**

```typescript
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
```

**注意**：检查 `trip-server/src/utils/logger.ts` 看 `alertLog` 是否已存在。如果没，加 `export const alertLog = baseLogger.child({ module: 'alert' })`。

- [ ] **Step 2: 写单元测试**

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest'

const mockCount = vi.fn()
const mockFindMany = vi.fn()

vi.mock('../../config/database', () => ({
  default: {
    feedback: {
      count: (...args: any[]) => mockCount(...args),
      findMany: (...args: any[]) => mockFindMany(...args),
    },
  },
}))

vi.mock('../../config/alert', () => ({
  loadAlertConfig: () => ({
    enabled: true,
    webhookUrl: 'http://test',
    webhookType: 'feishu' as const,
    threshold: 0.5,
    minFeedbacks: 5,
    intervalCron: '*/5 * * * *',
    windowMinutes: 60,
    dashboardUrl: 'http://localhost:5173',
  }),
}))

// 必须在 mock 之后 import（vi.mock 会被 hoist，但这里保险起见）
import { alertDetector } from '../alert/alertDetector'

describe('AlertDetector', () => {
  beforeEach(() => {
    mockCount.mockReset()
    mockFindMany.mockReset()
    mockFindMany.mockResolvedValue([])
  })

  it('5+ 反馈，rate < 0.5 → shouldAlert=true', async () => {
    mockCount.mockResolvedValueOnce(2)  // up
    mockCount.mockResolvedValueOnce(5)  // down
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(true)
    expect(result.stats.satisfactionRate).toBeCloseTo(0.286)  // 2/7
    expect(result.stats.feedbackCount).toBe(7)
  })

  it('5+ 反馈，rate ≥ 0.5 → shouldAlert=false', async () => {
    mockCount.mockResolvedValueOnce(6)  // up
    mockCount.mockResolvedValueOnce(2)  // down
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(false)
    expect(result.stats.satisfactionRate).toBeCloseTo(0.75)
  })

  it('< 5 反馈，rate < 0.5 → shouldAlert=false（样本太少）', async () => {
    mockCount.mockResolvedValueOnce(1)
    mockCount.mockResolvedValueOnce(2)
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(false)
    expect(result.reason).toContain('样本不足')
  })

  it('0 反馈 → shouldAlert=false', async () => {
    mockCount.mockResolvedValueOnce(0)
    mockCount.mockResolvedValueOnce(0)
    const result = await alertDetector.check()
    expect(result.shouldAlert).toBe(false)
    expect(result.stats.feedbackCount).toBe(0)
  })

  it('包含 recentDownComments（取最新 5 条）', async () => {
    mockCount.mockResolvedValueOnce(1)
    mockCount.mockResolvedValueOnce(5)
    mockFindMany.mockResolvedValueOnce([
      { comment: '推荐不准', tags: ['recommend'], createdAt: new Date() },
      { comment: '太慢', tags: ['speed'], createdAt: new Date() },
    ])
    const result = await alertDetector.check()
    expect(result.stats.recentDownComments).toHaveLength(2)
    expect(result.stats.recentDownComments[0].comment).toBe('推荐不准')
  })
})
```

- [ ] **Step 3: 跑测试**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm test src/services/__tests__/alertDetector.test.ts
```

Expected: 5 tests pass

- [ ] **Step 4: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/src/services/alert/alertDetector.ts trip-server/src/services/__tests__/alertDetector.test.ts
git commit -m "feat(alert): detector + 5 unit tests

  - alertDetector.check(): 查过去 1h feedback
  - shouldAlert = (total >= minFeedbacks) && (rate < threshold)
  - 5 单元测试：rate<0.5/正常/样本不足/0反馈/recentDownComments"
```

---

## Task 3: webhookNotifier.ts + 8 单元测试

**Files:**
- Create: `trip-server/src/services/alert/webhookNotifier.ts`
- Create: `trip-server/src/services/__tests__/webhookNotifier.test.ts`

- [ ] **Step 1: 写 webhookNotifier.ts**

```typescript
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

  /** 格式化 4 种 IM 格式的 payload */
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
            { type: 'section', text: { type: 'mrkdwn', text: `*${summary}*\n\n最近差评：\n${comments || '（无评论）'}` } },
            { type: 'actions', elements: [{ type: 'button', text: { type: 'plain_text', text: '查看 Dashboard' }, url: link }] },
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
```

- [ ] **Step 2: 写单元测试**

```typescript
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
    const p = webhookNotifier.formatPayload('feishu', { ...baseCheck, stats: { ...baseCheck.stats, recentDownComments: [] } }, 'http://localhost:5173')
    expect(p.card.elements[0].text.content).toContain('（无评论）')
  })
})

describe('WebhookNotifier - send', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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
    const r = await webhookNotifier.send(baseCheck)
    expect(r.success).toBe(true)
    expect(r.attempts).toBe(1)
    expect(mockFetch).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('发送失败 retry 3 次', async () => {
    mockLoadAlertConfig.mockReturnValue({ webhookUrl: 'http://test', webhookType: 'feishu' })
    const mockFetch = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    vi.stubGlobal('fetch', mockFetch)
    const r = await webhookNotifier.send(baseCheck)
    expect(r.success).toBe(false)
    expect(r.attempts).toBe(3)
    expect(mockFetch).toHaveBeenCalledTimes(3)
    vi.unstubAllGlobals()
  })

  it('网络异常 retry 3 次后失败', async () => {
    mockLoadAlertConfig.mockReturnValue({ webhookUrl: 'http://test', webhookType: 'feishu' })
    const mockFetch = vi.fn().mockRejectedValue(new Error('network'))
    vi.stubGlobal('fetch', mockFetch)
    const r = await webhookNotifier.send(baseCheck)
    expect(r.success).toBe(false)
    expect(r.attempts).toBe(3)
    expect(r.error).toBe('network')
    vi.unstubAllGlobals()
  })
})
```

- [ ] **Step 3: 跑测试**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm test src/services/__tests__/webhookNotifier.test.ts
```

Expected: 8 tests pass

- [ ] **Step 4: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/src/services/alert/webhookNotifier.ts trip-server/src/services/__tests__/webhookNotifier.test.ts
git commit -m "feat(alert): webhook notifier + 8 unit tests

  - 4 种 IM 格式：feishu/slack/dingtalk/wecom
  - 3 次 retry 指数退避（1s/3s/9s）
  - 失败只 warn log，不抛错
  - 8 单元测试：4 格式 + 空评论 + 未配置 + 成功 + 500 + 网络异常"
```

---

## Task 4: alertDeduplicator.ts

**Files:**
- Create: `trip-server/src/services/alert/alertDeduplicator.ts`

- [ ] **Step 1: 写 alertDeduplicator.ts**

```typescript
/**
 * 告警去重器
 *
 * Redis 5 分钟桶：alert:feedback:low:{timestamp}
 * 同窗口内不重发，避免告警轰炸
 *
 * Redis 不可用时旁路（不阻断告警，但可能重复）
 */

import redis, { isRedisAvailable } from '../../config/redis'
import { alertLog as log } from '../../utils/logger'

const BUCKET_MINUTES = 5
const TTL_SECONDS = BUCKET_MINUTES * 2 * 60  // 10 分钟（覆盖窗口 + 时钟偏移）

class AlertDeduplicator {
  private key(now: Date = new Date()): string {
    const bucketTs = Math.floor(now.getTime() / (BUCKET_MINUTES * 60 * 1000))
    return `alert:feedback:low:${bucketTs}`
  }

  /** 是否应该发送（未被去重） */
  async shouldSend(): Promise<boolean> {
    if (!isRedisAvailable()) {
      log.warn('Redis 不可用，告警去重旁路')
      return true
    }
    try {
      const k = this.key()
      const exists = await redis.exists(k)
      return exists === 0
    } catch (e) {
      log.warn({ err: e }, '去重检查失败，旁路')
      return true
    }
  }

  /** 标记已发送（10 分钟 TTL） */
  async markSent(): Promise<void> {
    if (!isRedisAvailable()) return
    try {
      const k = this.key()
      await redis.set(k, '1', 'EX', TTL_SECONDS)
    } catch (e) {
      log.warn({ err: e }, '标记告警已发送失败')
    }
  }
}

export const alertDeduplicator = new AlertDeduplicator()
```

**注意**：检查 `trip-server/src/config/redis.ts` 看 `isRedisAvailable` 是否导出。已经在断点续传任务用过——应该有。

- [ ] **Step 2: typecheck**

```bash
cd /Users/wang/Documents/trip/trip-server && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/src/services/alert/alertDeduplicator.ts
git commit -m "feat(alert): Redis 5min bucket deduplicator

  - bucket key: alert:feedback:low:{5min_timestamp}
  - TTL: 10min (覆盖 5min 桶 + 时钟偏移)
  - Redis 不可用旁路（不阻断告警）"
```

---

## Task 5: alertScheduler.ts + index.ts 集成

**Files:**
- Create: `trip-server/src/services/alert/alertScheduler.ts`
- Modify: `trip-server/src/index.ts`
- Modify: `trip-server/package.json`（加 node-cron 依赖）

- [ ] **Step 1: 装 node-cron**

```bash
cd /Users/wang/Documents/trip/trip-server && pnpm add node-cron
```

- [ ] **Step 2: 写 alertScheduler.ts**

```typescript
/**
 * 告警调度器
 *
 * 用 node-cron 每 5 分钟跑一次 alert check
 * 集成到 index.ts 启动时
 *
 * tick() 单独暴露，方便测试和手动触发
 */

import cron from 'node-cron'
import { loadAlertConfig } from '../../config/alert'
import { alertDetector } from './alertDetector'
import { webhookNotifier } from './webhookNotifier'
import { alertDeduplicator } from './alertDeduplicator'
import { alertLog as log } from '../../utils/logger'

class AlertScheduler {
  private task: cron.ScheduledTask | null = null

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

  /** 单次 tick —— 可供测试 / CLI 手动调用 */
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
```

- [ ] **Step 3: 集成到 index.ts**

在 `trip-server/src/index.ts` 找到 `app.listen(...)` 之后加：

```typescript
// 启动告警调度（仅 ALERT_ENABLED=true）
if (process.env.ALERT_ENABLED === 'true') {
  alertScheduler.start()
}

// graceful shutdown
const shutdown = () => {
  alertScheduler.stop()
  // ... 现有清理逻辑
}
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
```

加 import：

```typescript
import { alertScheduler } from './services/alert/alertScheduler'
```

- [ ] **Step 4: typecheck + 现有测试**

```bash
cd /Users/wang/Documents/trip/trip-server && npx tsc --noEmit
cd /Users/wang/Documents/trip/trip-server && pnpm test
```

Expected: 148 tests pass (135 + 13 = 148)

- [ ] **Step 5: Commit**

```bash
cd /Users/wang/Documents/trip && git add trip-server/src/services/alert/alertScheduler.ts trip-server/src/index.ts trip-server/package.json trip-server/pnpm-lock.yaml
git commit -m "feat(alert): scheduler + index integration

  - node-cron schedule per env ALERT_INTERVAL_CRON
  - tick(): detector → dedup → notifier
  - start/stop methods for graceful shutdown
  - 集成到 index.ts 启动（仅 ALERT_ENABLED=true）"
```

---

## Task 6: E2E 验证（httpbin）

- [ ] **Step 1: 启 server（无 ALERT）**

```bash
cd /Users/wang/Documents/trip/trip-server
pkill -f "nodemon\|dist/index" 2>/dev/null
sleep 2
nohup pnpm dev > /tmp/alert-e2e.log 2>&1 &
sleep 8
```

验证启动日志有"告警调度未启用"：
```bash
grep "告警调度" /tmp/alert-e2e.log
```

- [ ] **Step 2: 配 httpbin webhook**

httpbin.org/post 会 echo POST 内容，便于验证 payload。

- [ ] **Step 3: 重启 server（启用 ALERT）**

```bash
pkill -f "nodemon\|dist/index" 2>/dev/null
sleep 2
cd /Users/wang/Documents/trip/trip-server
ALERT_ENABLED=true \
ALERT_WEBHOOK_URL=https://httpbin.org/post \
ALERT_WEBHOOK_TYPE=feishu \
ALERT_THRESHOLD=0.5 \
ALERT_MIN_FEEDBACKS=2 \
ALERT_INTERVAL_CRON='*/5 * * * *' \
ALERT_WINDOW_MINUTES=60 \
nohup pnpm dev > /tmp/alert-e2e-on.log 2>&1 &
sleep 8
grep "告警调度已启动\|webhookUrl" /tmp/alert-e2e-on.log
```

Expected: "告警调度已启动"

- [ ] **Step 4: 创建测试 feedback（5 差评 + 1 好评）**

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"eval-test","password":"EvalTest@2026"}' | jq -r .data.token)

# 找 user 的 conversation
CONV_ID=$(cd /Users/wang/Documents/trip/trip-server && node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.conversation.findFirst({ where: { userId: 10 }, select: { id: true } })
  .then((c) => { console.log(c.id); p.\$disconnect(); });
")
echo "Conv ID: $CONV_ID"

# 创建 6 条差评 + 1 好评
for i in 1 2 3 4 5 6; do
  curl -s -X POST http://localhost:3000/api/feedback \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"messageId\":$i,\"conversationId\":$CONV_ID,\"rating\":-1,\"comment\":\"测试告警差评 #$i\",\"tags\":[\"test\"]}" > /dev/null
done
```

- [ ] **Step 5: 手动调 tick()（不等 5 分钟）**

可以加一个 admin endpoint 触发，或直接调 service：

```bash
cd /Users/wang/Documents/trip/trip-server
node -e "
const { alertScheduler } = require('./src/services/alert/alertScheduler');
alertScheduler.tick().then(r => console.log(JSON.stringify(r, null, 2)));
"
```

**注意**：上面的 node 调用会因为 ts-node 配置可能需要用 ts-node 跑。如果复杂，直接 curl 一个新的 admin endpoint（spec 里是 Out of Scope，但实战方便）。

**简化方案**：在 `feedback.routes.ts` 加一个 `POST /api/feedback/admin/test-alert` admin 端点，调 `alertScheduler.tick()`：

```typescript
import { alertScheduler } from '../../services/alert/alertScheduler'

router.post('/admin/test-alert', authMiddleware, async (req, res, next) => {
  try {
    if (req.user!.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '仅管理员可访问' })
    }
    const result = await alertScheduler.tick()
    res.json({ code: 200, data: result })
  } catch (e) {
    next(e)
  }
})
```

**然后**：
```bash
curl -s -X POST http://localhost:3000/api/feedback/admin/test-alert \
  -H "Authorization: Bearer $TOKEN" | jq
```

Expected: `{ code: 200, data: { shouldAlert: true, sent: true, reason: "..." } }`

- [ ] **Step 6: 检查 httpbin 收到 POST**

打开 https://httpbin.org/post 看最近的 POST 请求（httpbin 公开日志）。

- [ ] **Step 7: 验证去重（5min 桶）**

立即再调一次：
```bash
curl -s -X POST http://localhost:3000/api/feedback/admin/test-alert \
  -H "Authorization: Bearer $TOKEN" | jq
```

Expected: `{ shouldAlert: true, sent: false, reason: "..." }`（被去重）

- [ ] **Step 8: 关闭 server**

```bash
pkill -f "nodemon\|dist/index" 2>/dev/null
```

- [ ] **Step 9: Commit（如果有改动）**

```bash
cd /Users/wang/Documents/trip
git add trip-server/src/routes/feedback.routes.ts
git commit -m "test(alert): admin test-alert endpoint for E2E verification"
```

---

## Task 7: 文档

**Files:**
- Create: `docs/alert-system.md`
- Modify: `tasks/todo.md`（标 §1 自动告警完成）

- [ ] **Step 1: 写 docs/alert-system.md**

```markdown
# Feedback 自动告警系统

> 配套 `docs/online-feedback.md`、`docs/feedback-dashboard.md`

## 目标

feedback 满意率低时**自动发 IM 告警**——飞书/Slack/钉钉/企业微信，owner 不需要盯 dashboard 也能知道质量问题。

## 架构

\`\`\`
每 5 分钟 (cron)
  ↓
alertDetector.check()  查过去 1h feedback
  ↓
rate < 0.5 AND total >= 5?
  ↓ 是
alertDeduplicator.shouldSend()  Redis 5min 桶去重
  ↓ 是
webhookNotifier.send()  4 种 IM 格式之一
  ↓
markSent()  Redis 10min TTL
\`\`\`

## 启用

### 1. 配环境变量

\`\`\`bash
# .env 或 export
ALERT_ENABLED=true
ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx
ALERT_WEBHOOK_TYPE=feishu
ALERT_THRESHOLD=0.5
ALERT_MIN_FEEDBACKS=5
ALERT_INTERVAL_CRON='*/5 * * * *'
ALERT_WINDOW_MINUTES=60
DASHBOARD_URL=https://your-domain.com
\`\`\`

### 2. 重启 server

\`\`\`bash
cd trip-server
pnpm dev
\`\`\`

日志应出现：
\`\`\`
告警调度已启动 cron="*/5 * * * *" type=feishu threshold=0.5 minFeedbacks=5 windowMinutes=60
\`\`\`

## 4 种 Webhook 配置示例

### 飞书

\`\`\`bash
ALERT_WEBHOOK_TYPE=feishu
ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/<your-hook-id>
\`\`\`

**飞书机器人创建**：群 → 设置 → 群机器人 → 添加机器人 → 自定义 webhook → 复制 hook URL

### Slack

\`\`\`bash
ALERT_WEBHOOK_TYPE=slack
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
\`\`\`

**Slack webhook 创建**：https://api.slack.com/messaging/webhooks → Create your Slack app → Incoming Webhooks

### 钉钉

\`\`\`bash
ALERT_WEBHOOK_TYPE=dingtalk
ALERT_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxxxx
\`\`\`

**钉钉机器人创建**：群 → 群设置 → 智能群助手 → 添加机器人 → 自定义 → 复制 webhook

### 企业微信

\`\`\`bash
ALERT_WEBHOOK_TYPE=wecom
ALERT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxx
\`\`\`

**企业微信机器人创建**：群 → 右键 → 群机器人 → 添加 → 复制 webhook URL

## 测试（手动触发）

\`\`\`bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \\
  -H "Content-Type: application/json" \\
  -d '{"username":"admin","password":"..."}' | jq -r .data.token)

curl -X POST http://localhost:3000/api/feedback/admin/test-alert \\
  -H "Authorization: Bearer $TOKEN" | jq
\`\`\`

Expected: \`{ code: 200, data: { shouldAlert: true, sent: true, reason: "..." } }\`

Webhook 收到后，5 分钟桶去重，再调一次返回 \`sent: false\`。

## 环境变量说明

| 变量 | 默认 | 说明 |
|---|---|---|
| \`ALERT_ENABLED\` | \`false\` | 是否启用调度（必须显式开启）|
| \`ALERT_WEBHOOK_URL\` | 空 | webhook URL（required if enabled）|
| \`ALERT_WEBHOOK_TYPE\` | \`feishu\` | feishu/slack/dingtalk/wecom |
| \`ALERT_THRESHOLD\` | \`0.5\` | 满意率阈值（0-1）|
| \`ALERT_MIN_FEEDBACKS\` | \`5\` | 最小反馈数（防误报）|
| \`ALERT_INTERVAL_CRON\` | \`*/5 * * * *\` | 调度频率 |
| \`ALERT_WINDOW_MINUTES\` | \`60\` | 查询窗口 |
| \`DASHBOARD_URL\` | \`http://localhost:5173\` | 告警中链接的 dashboard 地址 |

## 限制

- **仅 satisfactionRate 告警**：cache 命中率、0 反馈静默等暂未做（YAGNI）
- **5min 去重**：高频告警不会轰炸，但可能漏掉新的告警
- **失败只 warn**：webhook 失败不抛错，避免影响主流程
- **无 AlertHistory 表**：告警历史不持久化（v2）

## 关键设计决策

1. **完整告警系统**（B 方案）：4 个 service 各司其职
2. **4 种 IM 格式**：覆盖主流 IM，不做适配器模式（简单 if/switch）
3. **5min cron + 10min TTL 去重**：防轰炸
4. **Redis 旁路降级**：不阻断告警
5. **3 次 retry 指数退避**：网络抖动容错
6. **ALERT_ENABLED 默认 false**：显式开启（防意外告警）
7. **minFeedbacks=5**：防样本太少误报
8. **失败不抛**：warn log + 返回 SendResult
9. **tick() 暴露**：测试和 CLI 手动触发
\`\`\`

### 2. 更新 tasks/todo.md

找到：
```
- ⏳ **自动告警**：连续 1 小时 satisfactionRate < 0.5 触发飞书/Slack
```

改为：
```
- ✅ **自动告警**：完整告警系统已交付（detector + 4 种 webhook + Redis 去重 + cron）—— 详见 `docs/alert-system.md`
```

### 3. 更新 docs/online-feedback.md

找到 "后续进度" 区段：
```
- ⏳ **自动告警**：连续 1 小时 satisfactionRate < 0.5 触发飞书/Slack 告警（暂未做）
```

改为：
```
- ✅ **自动告警**：完整告警系统（2026-06-25 完成）—— 详见 `docs/alert-system.md`
```

### 4. Commit

```bash
cd /Users/wang/Documents/trip
git add docs/alert-system.md tasks/todo.md docs/online-feedback.md
git commit -m "docs: alert system usage guide + mark §1 alert done

  - docs/alert-system.md (NEW):
    * 启用步骤（环境变量）
    * 4 种 webhook 配置示例（飞书/Slack/钉钉/企业微信）
    * 测试方法（admin test-alert endpoint）
    * 环境变量说明
    * 限制 + 关键设计决策
  - tasks/todo.md: §1 自动告警 ✅
  - docs/online-feedback.md: 后续进度更新"
```

---

## 验证清单

跑完所有 Task 后，最终检查：

- [ ] `pnpm test` 通过（135 + 13 = 148 测试）
- [ ] `pnpm typecheck` clean
- [ ] E2E：httpbin 收到 POST + payload 是 feishu 格式
- [ ] 去重验证：立即再调返回 `sent: false`
- [ ] 关闭 `ALERT_ENABLED` 时 scheduler 不启动
- [ ] Webhook 失败 retry 3 次（mock fetch 验证）
- [ ] Redis 不可用时仍能告警（旁路去重）
- [ ] `docs/alert-system.md` 完整

## 总 commit 清单

1. `feat(alert): config loader with env var validation`
2. `feat(alert): detector + 5 unit tests`
3. `feat(alert): webhook notifier + 8 unit tests`
4. `feat(alert): Redis 5min bucket deduplicator`
5. `feat(alert): scheduler + index integration`
6. `test(alert): admin test-alert endpoint for E2E`
7. `docs: alert system usage guide + mark §1 alert done`
