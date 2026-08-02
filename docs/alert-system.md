# Feedback 自动告警系统

> 配套 `docs/online-feedback.md`、`docs/feedback-dashboard.md`

## 目标

feedback 满意率低时**自动发 IM 告警**——飞书/Slack/钉钉/企业微信，owner 不需要盯 dashboard 也能知道质量问题。

```
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
```

## 启用

### 1. 配环境变量

```bash
# .env 或 export
ALERT_ENABLED=true
ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx
ALERT_WEBHOOK_TYPE=feishu
ALERT_THRESHOLD=0.5
ALERT_MIN_FEEDBACKS=5
ALERT_INTERVAL_CRON='*/5 * * * *'
ALERT_WINDOW_MINUTES=60
DASHBOARD_URL=https://your-domain.com
```

### 2. 重启 server

```bash
cd trip-server
pnpm dev
```

日志应出现：
```
告警调度已启动 cron="*/5 * * * *" type=feishu threshold=0.5 minFeedbacks=5 windowMinutes=60
```

## 4 种 Webhook 配置示例

### 飞书

```bash
ALERT_WEBHOOK_TYPE=feishu
ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/<your-hook-id>
```

**飞书机器人创建**：群 → 设置 → 群机器人 → 添加机器人 → 自定义 webhook → 复制 hook URL

### Slack

```bash
ALERT_WEBHOOK_TYPE=slack
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
```

**Slack webhook 创建**：https://api.slack.com/messaging/webhooks → Create your Slack app → Incoming Webhooks

### 钉钉

```bash
ALERT_WEBHOOK_TYPE=dingtalk
ALERT_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxxxx
```

**钉钉机器人创建**：群 → 群设置 → 智能群助手 → 添加机器人 → 自定义 → 复制 webhook

### 企业微信

```bash
ALERT_WEBHOOK_TYPE=wecom
ALERT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxx
```

**企业微信机器人创建**：群 → 右键 → 群机器人 → 添加 → 复制 webhook URL

## 测试（手动触发）

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"..."}' | jq -r .data.token)

curl -X POST http://localhost:3000/api/feedback/admin/test-alert \
  -H "Authorization: Bearer $TOKEN" | jq
```

Expected: `{ code: 200, data: { shouldAlert: true, sent: true, reason: "..." } }`

Webhook 收到后，5 分钟桶去重，再调一次返回 `sent: false`。

## 环境变量说明

| 变量 | 默认 | 说明 |
|---|---|---|
| `ALERT_ENABLED` | `false` | 是否启用调度（必须显式开启）|
| `ALERT_WEBHOOK_URL` | 空 | webhook URL（required if enabled）|
| `ALERT_WEBHOOK_TYPE` | `feishu` | feishu/slack/dingtalk/wecom |
| `ALERT_THRESHOLD` | `0.5` | 满意率阈值（0-1）|
| `ALERT_MIN_FEEDBACKS` | `5` | 最小反馈数（防误报）|
| `ALERT_INTERVAL_CRON` | `*/5 * * * *` | 调度频率 |
| `ALERT_WINDOW_MINUTES` | `60` | 查询窗口 |
| `DASHBOARD_URL` | `http://localhost:5173` | 告警中链接的 dashboard 地址 |

## 限制

- **仅 satisfactionRate 告警**：cache 命中率、0 反馈静默等暂未做（YAGNI）
- **5min 去重**：高频告警不会轰炸，但可能漏掉新的告警
- **失败只 warn**：webhook 失败不抛错，避免影响主流程
- **无 AlertHistory 表**：告警历史不持久化（v2）

## 关键设计决策

1. **完整告警系统**：4 个 service 各司其职
2. **4 种 IM 格式**：覆盖主流 IM
3. **5min cron + 10min TTL 去重**：防轰炸
4. **Redis 旁路降级**：不阻断告警
5. **3 次 retry 指数退避**：网络抖动容错
6. **ALERT_ENABLED 默认 false**：显式开启（防意外告警）
7. **minFeedbacks=5**：防样本太少误报
8. **失败不抛**：warn log + 返回 SendResult
9. **tick() 暴露**：测试和 CLI 手动触发
