# 反馈自动告警系统 设计

> 配套 `docs/online-feedback.md` 后续、`docs/feedback-dashboard.md`
> 关联 commits：`273a6a2`（反馈系统）、`6586425`（admin dashboard）

## 目标

当 feedback 满意度低于阈值时**自动发飞书/Slack/钉钉告警**——让 owner 不需要一直盯 dashboard 也能知道质量出问题。

```
每 5 分钟跑一次：
  ↓
查过去 1 小时 feedback
  ↓
if satisfactionRate < 0.5 AND 反馈数 >= 5:
    发 webhook 告警
    5 分钟内同类不重发（Redis 去重 key）
```

**价值**：
- **生产必需**：没有告警，agent 退化几天用户走了都不知道
- **主动响应**：从"看 dashboard 发现问题"变成"系统主动通知"
- **解耦**：用 webhook 适配飞书/Slack/钉钉/企业微信，不需要每家单独集成

---

## 范围

### In Scope

1. **告警检测器** `services/alertDetector.ts`
   - 查过去 1 小时 feedback
   - 计算 satisfactionRate
   - 阈值判断：`< 0.5` AND `反馈数 >= 5`（避免样本太少误报）

2. **Webhook 发送器** `services/webhookNotifier.ts`
   - 适配飞书/Slack/钉钉/企业微信（4 种格式）
   - 环境变量配置：`ALERT_WEBHOOK_URL` + `ALERT_WEBHOOK_TYPE`（`feishu`/`slack`/`dingtalk`/`wecom`）
   - 失败 retry 3 次（指数退避）
   - 失败只 warn log，不抛错

3. **告警去重** `services/alertDeduplicator.ts`
   - Redis key `alert:feedback:low:{window}`（window = 时间桶，5 分钟粒度）
   - 5 分钟内同类不重发
   - 用现有 `redis.ts` 客户端

4. **定时调度** `services/alertScheduler.ts`
   - 用 `node-cron` 每 5 分钟跑一次
   - 集成到 `src/index.ts` 启动时
   - 环境变量开关 `ALERT_ENABLED`（默认 false，配置好 webhook 后开启）

5. **配置**
   - `ALERT_ENABLED`（bool，默认 false）
   - `ALERT_WEBHOOK_URL`（string，required if enabled）
   - `ALERT_WEBHOOK_TYPE`（`feishu`/`slack`/`dingtalk`/`wecom`，默认 `feishu`）
   - `ALERT_THRESHOLD`（0-1，默认 0.5）
   - `ALERT_MIN_FEEDBACKS`（int，默认 5）
   - `ALERT_INTERVAL_CRON`（cron expr，默认 `*/5 * * * *`）
   - `ALERT_WINDOW_MINUTES`（int，默认 60）

6. **文档** `docs/alert-system.md`
   - 4 种 webhook 配置示例
   - 环境变量说明
   - 测试方法（手动触发）

### Out of Scope

- ❌ 多种告警类型（cache 命中率、0 反馈静默等）—— YAGNI
- ❌ AlertHistory 表持久化 —— v2
- ❌ 邮件告警 —— webhook 覆盖主流
- ❌ 告警升级（多次告警不同时段）—— v2
- ❌ 静默规则（"每天只发 1 次"）—— Redis 5min 去重已够用

---

## 架构

### 1. 文件结构

```
trip-server/
├── src/
│   ├── services/
│   │   ├── alert/
│   │   │   ├── alertDetector.ts       # NEW 检测器
│   │   │   ├── webhookNotifier.ts     # NEW 发送器
│   │   │   ├── alertDeduplicator.ts   # NEW 去重
│   │   │   └── alertScheduler.ts      # NEW 调度器
│   │   └── __tests__/
│   │       ├── alertDetector.test.ts  # NEW 单测
│   │       └── webhookNotifier.test.ts # NEW 单测
│   ├── config/
│   │   └── alert.ts                   # NEW 配置加载
│   ├── index.ts                       # 启动时 initAlertScheduler()
docs/
└── alert-system.md                    # NEW 使用文档
```

### 2. 数据流

```
index.ts 启动
  ↓
initAlertScheduler()（仅 ALERT_ENABLED=true）
  ↓
node-cron 每 5 分钟
  ↓
alertScheduler.tick()
  ↓
alertDetector.check() → { shouldAlert, stats: { rate, count, recentComments } }
  ↓
if shouldAlert:
    alertDeduplicator.shouldSend(window='5min') → bool
    if shouldSend:
        webhookNotifier.send({ type, title, body, recentComments })
        ↓
        4 种格式：
        - feishu:  { msg_type: 'interactive', card: {...} }
        - slack:   { text, blocks: [...] }
        - dingtalk: { msgtype: 'markdown', markdown: {...} }
        - wecom:   { msgtype: 'markdown', markdown: {...} }
        ↓
        POST ALERT_WEBHOOK_URL
        ↓
        失败 retry 3 次（1s/3s/9s 退避）
        alertDeduplicator.markSent(window='5min')
```

### 3. alertDetector 设计

```typescript
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
  /** 查过去 N 分钟 feedback，判断是否需要告警 */
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
    return {
      shouldAlert,
      reason: shouldAlert
        ? `过去 ${cfg.windowMinutes} 分钟 ${total} 条反馈，满意率 ${(rate * 100).toFixed(1)}% < ${(cfg.threshold * 100).toFixed(0)}%`
        : `正常：${total} 条反馈，满意率 ${(rate * 100).toFixed(1)}%`,
      stats: { feedbackCount: total, upCount: up, downCount: down, satisfactionRate: rate, recentDownComments: [...] },
      threshold: cfg.threshold,
      minFeedbacks: cfg.minFeedbacks,
    }
  }
}
```

### 4. webhookNotifier 设计

```typescript
type WebhookType = 'feishu' | 'slack' | 'dingtalk' | 'wecom'

class WebhookNotifier {
  async send(check: AlertCheckResult): Promise<{ success: boolean; attempts: number; error?: string }> {
    const cfg = loadAlertConfig()
    if (!cfg.webhookUrl) return { success: false, attempts: 0, error: 'webhookUrl 未配置' }
    
    const payload = this.formatPayload(cfg.webhookType, check)
    
    // 3 次 retry，指数退避
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await fetch(cfg.webhookUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (res.ok) return { success: true, attempts: attempt + 1 }
      } catch (e) {
        if (attempt === 2) return { success: false, attempts: 3, error: e.message }
      }
      await new Promise(r => setTimeout(r, 1000 * Math.pow(3, attempt)))  // 1s, 3s, 9s
    }
    return { success: false, attempts: 3, error: 'all retries failed' }
  }
  
  private formatPayload(type: WebhookType, check: AlertCheckResult): any {
    const title = '⚠️ Feedback 满意率告警'
    const summary = check.reason
    const comments = check.stats.recentDownComments
      .map(c => `- ${c.comment} [${(c.tags || []).join(', ')}]`)
      .join('\n')
    const dashboardLink = `${process.env.DASHBOARD_URL || 'http://localhost:5173'}/admin/feedback`
    
    switch (type) {
      case 'feishu':
        return {
          msg_type: 'interactive',
          card: {
            header: { title: { tag: 'plain_text', content: title } },
            elements: [
              { tag: 'div', text: { tag: 'lark_md', content: `**${summary}**\n${comments}` } },
              { tag: 'action', actions: [{ tag: 'button', text: { tag: 'plain_text', content: '查看 Dashboard' }, type: 'primary', url: dashboardLink }] },
            ],
          },
        }
      case 'slack':
        return {
          text: title,
          blocks: [
            { type: 'section', text: { type: 'mrkdwn', text: `*${summary}*\n${comments}` } },
            { type: 'actions', elements: [{ type: 'button', text: { type: 'plain_text', text: '查看 Dashboard' }, url: dashboardLink }] },
          ],
        }
      case 'dingtalk':
        return {
          msgtype: 'markdown',
          markdown: { title, text: `**${summary}**\n\n${comments}\n\n[查看 Dashboard](${dashboardLink})` },
        }
      case 'wecom':
        return {
          msgtype: 'markdown',
          markdown: { content: `**${title}**\n\n${summary}\n\n${comments}` },
        }
    }
  }
}
```

### 5. alertDeduplicator 设计

```typescript
class AlertDeduplicator {
  /** 5 分钟桶：alert:feedback:low:2026-06-25T15:30 */
  private key(windowStart: Date): string {
    const ts = Math.floor(windowStart.getTime() / (5 * 60 * 1000))
    return `alert:feedback:low:${ts}`
  }
  
  async shouldSend(): Promise<boolean> {
    if (!isRedisAvailable()) return true  // Redis 挂了不阻断告警
    const k = this.key(new Date())
    const exists = await redis.exists(k)
    return exists === 0
  }
  
  async markSent(): Promise<void> {
    if (!isRedisAvailable()) return
    const k = this.key(new Date())
    await redis.set(k, '1', 'EX', 600)  // 10 分钟 TTL（覆盖 5min 桶 + 时钟偏移）
  }
}
```

### 6. alertScheduler 设计

```typescript
import cron from 'node-cron'

class AlertScheduler {
  private task: cron.ScheduledTask | null = null
  private detector = new AlertDetector()
  private notifier = new WebhookNotifier()
  private dedup = new AlertDeduplicator()
  
  start() {
    const cfg = loadAlertConfig()
    if (!cfg.enabled) {
      log.info('告警调度未启用（ALERT_ENABLED=false）')
      return
    }
    if (!cfg.webhookUrl) {
      log.warn('ALERT_ENABLED=true 但 ALERT_WEBHOOK_URL 未配置，跳过')
      return
    }
    this.task = cron.schedule(cfg.intervalCron, () => this.tick().catch(e => log.error(e)))
    log.info({ cron: cfg.intervalCron, type: cfg.webhookType }, '告警调度已启动')
  }
  
  stop() {
    this.task?.stop()
  }
  
  /** 单次 tick —— 也供测试调用 */
  async tick(): Promise<void> {
    const check = await this.detector.check()
    if (!check.shouldAlert) {
      log.debug({ reason: check.reason }, '告警检查：正常')
      return
    }
    if (!(await this.dedup.shouldSend())) {
      log.info({ reason: check.reason }, '告警已被去重（5min 桶内已发送）')
      return
    }
    const result = await this.notifier.send(check)
    if (result.success) {
      await this.dedup.markSent()
      log.info({ attempts: result.attempts, reason: check.reason }, '告警已发送')
    } else {
      log.error({ error: result.error, attempts: result.attempts }, '告警发送失败')
    }
  }
}
```

### 7. config/alert.ts

```typescript
export interface AlertConfig {
  enabled: boolean
  webhookUrl: string
  webhookType: 'feishu' | 'slack' | 'dingtalk' | 'wecom'
  threshold: number
  minFeedbacks: number
  intervalCron: string
  windowMinutes: number
}

export function loadAlertConfig(): AlertConfig {
  return {
    enabled: process.env.ALERT_ENABLED === 'true',
    webhookUrl: process.env.ALERT_WEBHOOK_URL || '',
    webhookType: (process.env.ALERT_WEBHOOK_TYPE as any) || 'feishu',
    threshold: Number(process.env.ALERT_THRESHOLD) || 0.5,
    minFeedbacks: Number(process.env.ALERT_MIN_FEEDBACKS) || 5,
    intervalCron: process.env.ALERT_INTERVAL_CRON || '*/5 * * * *',
    windowMinutes: Number(process.env.ALERT_WINDOW_MINUTES) || 60,
  }
}
```

### 8. index.ts 集成

```typescript
import { alertScheduler } from './services/alert/alertScheduler'

// ... 现有启动代码 ...

// 在 server.listen() 后
if (process.env.ALERT_ENABLED === 'true') {
  alertScheduler.start()
}

// graceful shutdown
process.on('SIGTERM', () => {
  alertScheduler.stop()
  // ... 其他清理
})
```

---

## 错误处理

| 场景 | 行为 |
|---|---|
| `ALERT_WEBHOOK_URL` 未配置 | log warn，scheduler 不启动 |
| Redis 不可用 | 去重旁路（不阻断告警），warn log |
| Webhook 发送失败 | 3 次 retry，1s/3s/9s 退避，最终 warn log |
| `prisma.feedback` 查询失败 | error log，下个 tick 再试 |
| node-cron 表达式非法 | 启动时 validate，失败抛错 |
| `ALERT_THRESHOLD` 非法（>1 / <0）| 启动时 clamp 到 0-1 |
| 告警发送成功 | markSent 写 Redis TTL 10min |

---

## 测试

### 1. 单元测试

**alertDetector.test.ts（5 个测试）**：
- ✅ 5+ 反馈，rate < 0.5 → shouldAlert=true
- ✅ 5+ 反馈，rate ≥ 0.5 → shouldAlert=false
- ✅ < 5 反馈，rate < 0.5 → shouldAlert=false（样本太少）
- ✅ 0 反馈 → shouldAlert=false
- ✅ 包含 recentDownComments（取最新 5 条）

**webhookNotifier.test.ts（8 个测试）**：
- ✅ feishu 格式 payload
- ✅ slack 格式 payload
- ✅ dingtalk 格式 payload
- ✅ wecom 格式 payload
- ✅ URL 未配置 → success=false
- ✅ 发送成功（mock fetch）
- ✅ 发送失败 retry 3 次
- ✅ 3 次都失败 → 返回 error

### 2. E2E（手动）

- 配 ALERT_WEBHOOK_URL 指向 httpbin.org/post
- ALERT_ENABLED=true
- 创建 6 条反馈（1 好评 + 5 差评）
- 等下一个 5 分钟 tick（或手动调 scheduler.tick()）
- 检查 httpbin.org/post 收到 POST

### 3. typecheck

- `pnpm typecheck` clean

---

## 实施步骤

1. **`config/alert.ts`**：配置加载（带 env var 校验）
2. **`alertDetector.ts` + 单测**：检测器
3. **`webhookNotifier.ts` + 单测**：4 种格式 + retry
4. **`alertDeduplicator.ts`**：Redis 5min 桶去重
5. **`alertScheduler.ts` + 集成到 index.ts**：cron + tick
6. **E2E 验证**：用 httpbin.org 模拟
7. **文档** `docs/alert-system.md`

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Webhook URL 泄露（commit 到 git）| README 强调用环境变量，`.env` 加 `.gitignore`（已有）|
| 误报（1 个差评就告警）| `minFeedbacks=5` 兜底|
| Webhook 服务挂了 | retry 3 次 + 失败不抛（只 warn）|
| Redis 挂 | 去重旁路（仍告警，可能重复）|
| Cron 表达式错 | 启动时 validate `cron.validate(expr)`|
| 时钟漂移导致漏发 | 5min 桶 + 10min TTL 留余量|
| 高频告警轰炸 | Redis 去重 5min 内不重发（够用）|

---

## 验证标准

1. `pnpm test` 通过（135 + 13 = 148 测试）
2. `pnpm typecheck` clean
3. E2E：httpbin 收到 POST 请求 + payload 是 4 种格式之一
4. 关闭 `ALERT_ENABLED` 时 scheduler 不启动（log 提示）
5. Webhook 失败 retry 3 次（mock fetch 验证）
6. Redis 不可用时仍能告警（旁路去重）

---

## 关键决策摘要

1. **完整告警系统**（B 方案）：检测器 + Webhook + 调度器 + 集成
2. **仅 satisfactionRate < 0.5**（A 条件）：聚焦核心问题
3. **4 种 webhook 格式**（飞书/Slack/钉钉/企业微信）：覆盖主流 IM
4. **5min cron + 10min TTL 去重**：防轰炸
5. **Redis 旁路降级**：Redis 挂不阻断告警
6. **3 次 retry 指数退避**：网络抖动容错
7. **默认 ALERT_ENABLED=false**：显式开启（防意外告警）
8. **环境变量配置**：适配不同部署
