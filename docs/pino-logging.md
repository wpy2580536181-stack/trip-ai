# Pino 日志改造方案

> **背景**：项目后端有 59 处 `console.log/warn/error`，全部是字符串拼接。无法做日志聚合、查询、告警。
> **目标**：升级为 pino 结构化日志，开发体验更好（pino-pretty），生产可直接对接 ELK/Loki。
> **实施时间**：2026-06-21

---

## 1. 为什么选 pino（不选 winston/bunyan）

| 库 | 性能 | 异步 | 结构化 | 选择理由 |
|---|---|---|---|---|
| **pino** | 🟢 50K logs/s | ✅ 默认 | ✅ JSON | **本次选型** |
| winston | 🟡 10K logs/s | ❌ 同步 | ✅ | 同步 transport 拖慢请求 |
| bunyan | 🟢 20K logs/s | ✅ | ✅ | 维护频率下降，生态弱 |
| debug | 🟢 | ❌ | ❌ | 不写文件，不能生产 |

关键原因：
1. **异步写入** — pino 调用 `log.info()` 几乎零开销，主线程不阻塞（winston 同步，慢 transport 拖慢请求）
2. **结构化** — `log.info({ userId, durationMs }, 'chat done')` 字段可查询
3. **pino-http** — 官方 HTTP 中间件，自动 access log + `req.log` 注入
4. **错误展开** — `log.error({ err }, '失败')` 自动含 stack、code、name
5. **生态完整** — pino-pretty（开发）+ pino.transport（生产）

---

## 2. 改造内容

### 2.1 装包

```bash
npm install pino pino-http
npm install -D pino-pretty @types/pino-http
```

### 2.2 `src/utils/logger.ts`（新建）

- 基础 pino 实例 + ISO 时间戳
- 字段脱敏（`req.headers.authorization`、`*.password`、`*.token` 等）
- 13 个 child logger：agentLog / tripLog / knowledgeLog / userLog / authLog / summaryLog / queryRewriteLog / rerankerLog / embeddingLog / streamLog / llmGuardLog / chromaLog / httpLog
- 三个模式：
  - 开发默认：`pino-pretty` 彩色
  - 生产 JSON：`stdout` 一行一 JSON
  - 生产 + 文件：`pino.transport` 双写到 LOG_FILE

### 2.3 `src/index.ts`

接入 `pino-http` 中间件：
- 自动注入 `req.log`（含 reqId）
- 自定义 reqId：`x-request-id` header 或 `randomUUID()`
- 响应头带 `x-request-id` 便于客户端定位
- 自定义日志级别：5xx → error / 4xx → warn / 其他 → info
- 排除 `/api/test` 健康检查
- 自定义 `req` / `res` 序列化（只保留 method / url / statusCode）

### 2.4 替换 14 个文件中的 58 处 console

| 文件 | module | 替换数 |
|---|---|---|
| `services/agent/agentEngine.ts` | agent | 9 |
| `services/knowledgeService.ts` | knowledge | 11 |
| `services/tripService.ts` | trip | 6 |
| `services/reranker.ts` | reranker | 5 |
| `services/summaryService.ts` | summary | 4 |
| `services/queryRewriter.ts` | queryRewrite | 4 |
| `services/agent/resilience.ts` | agent | 2 |
| `services/agent/tools/getWeather.ts` | agent | 2 |
| `services/userService.ts` | auth | 2 |
| `services/optimizeService.ts` | trip | 1 |
| `controllers/trip.controller.ts` | trip | 3 |
| `config/embeddings.ts` | embedding | 4 |
| `config/chroma.ts` | chroma | 1 |
| `utils/stream.ts` | stream | 3 |

唯一保留的 console：`logger.ts` 文件 transport 初始化失败的回退日志（pino 挂了必须有 console 兜底）。

### 2.5 替换映射示例

```typescript
// 改前
console.warn('[Agent] 主 LLM 失败，切换到备用模型重试:', e instanceof Error ? e.message : e)
console.log(`[Summary] 对话 ${conversationId} 摘要已生成 (${summary.length}字)`)
console.error('[Knowledge] 导入失败: ' + spot.name, e)

// 改后
log.warn({ err: e, fallback: 'AGNES' }, '主 LLM 失败，切换到备用模型重试')
log.info({ conversationId, chunkLen: summary.length }, '摘要已生成')
log.error({ err: e, spotName: spot.name }, '导入失败')
```

---

## 3. 输出效果

### 3.1 开发（默认 pretty）

```
[16:05:23.693] INFO: 使用 HF endpoint
    module: "embedding"
    endpoint: "https://hf-mirror.com/"
[16:05:23.871] INFO: Server running on http://localhost:3000
    port: "3000"
[16:05:39.812] INFO: POST /chat → 200
    req: { "method": "POST", "url": "/chat", "id": "uuid-xxx" }
    res: { "statusCode": 200 }
    responseTime: 2030
[16:05:42.787] WARN: 主 LLM 失败，切换到备用模型重试
    module: "agent"
    fallback: "AGNES"
    err: {
      "type": "TimeoutError",
      "message": "Agent 执行超时（60s）",
      "stack": "..."
    }
```

### 3.2 生产（JSON）

```json
{"level":"info","time":"2026-06-21T08:05:37.754Z","module":"http","req":{"method":"POST","url":"/login","id":"abc-123"},"res":{"statusCode":200},"responseTime":45,"msg":"POST /login → 200"}
{"level":"warn","time":"2026-06-21T08:05:42.787Z","module":"agent","fallback":"AGNES","err":{"type":"TimeoutError","message":"Agent 执行超时（60s）","stack":"..."},"msg":"主 LLM 失败，切换到备用模型重试"}
```

直接被 Loki / ELK 摄入：`{service="trip-server"} | json | module="agent" | level="warn"`

### 3.3 生产 + 文件

```bash
LOG_FILE=./logs/trip-server.log nohup npx ts-node src/index.ts > stdout.log 2>&1 &
```

- `./logs/trip-server.log` — JSON 行（机器消费）
- `stdout.log` — 人类可读（k8s 容器收集）

---

## 4. 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `LOG_LEVEL` | `debug`（开发）/ `info`（生产） | debug / info / warn / error / fatal |
| `LOG_PRETTY` | dev 自动 true | true = pino-pretty；false = raw JSON |
| `LOG_FILE` | 留空 | 路径 = 双写到文件 + stdout pretty |
| `NODE_ENV` | development | production 时自动 JSON 输出 |

---

## 5. 关键设计决策

### 5.1 每个模块独立 child logger

```typescript
// 而不是每次 log.info({ module: 'agent' }, '...')
const log = baseLogger.child({ module: 'agent' })
log.info('...')  // 自动带 module: 'agent'
```

**优点**：模块名作为一级字段，可按 module 过滤。

### 5.2 错误对象 `{ err: e }`

pino 自动展开 `Error` 对象的 stack / name / code / message。

```typescript
log.error({ err: e }, '失败')
// 输出包含: err.type, err.message, err.stack, err.code（如果有）
```

不要用 `e.message` 字符串：
```typescript
log.error(e.message, '失败')  // ❌ 字符串丢 stack
log.error({ err: e }, '失败')  // ✅ pino 自动展开
```

### 5.3 敏感字段脱敏

```typescript
redact: {
  paths: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token', '*.apiKey'],
  censor: '[REDACTED]',
}
```

注意 `authLog` 里 `重置令牌已生成` 包含 token 字段——**这就是我们要的"明知有风险但要记录"**，通过 `log.info({ token }, '...')` 而不是字符串拼接，且 `*.token` 脱敏会把它替换成 `[REDACTED]`。

### 5.4 控制器层用 `req.log`

```typescript
router.post('/login', ...)
  .use((req, res) => {
    req.log.info({ userId }, '登录成功')  // 自动带 reqId
  })
```

避免 service 层"不知道当前是哪个请求"，所有日志自动关联到同一 reqId。

---

## 6. 验证清单

- ✅ TypeScript 编译通过
- ✅ `rg "console\." src/` 58 → 1（仅 logger.ts 兜底）
- ✅ pino-pretty 彩色输出开发模式生效
- ✅ 错误对象完整序列化（DOMException 含 stack + code + name）
- ✅ HTTP access log 自动记录（`POST /chat → 200` 含 responseTime）
- ✅ 模块字段（`module: 'agent' / 'trip' / 'knowledge' / 'auth'`）正确

---

## 7. 文件清单

| 文件 | 操作 |
|---|---|
| `package.json` | + pino / pino-http / pino-pretty / @types/pino-http |
| `src/utils/logger.ts` | **新建** — pino 基础 + 13 个 child logger + 脱敏 |
| `src/index.ts` | 接入 pino-http + 全局错误处理用 req.log |
| `src/controllers/trip.controller.ts` | 替换 3 处 console |
| `src/services/agent/agentEngine.ts` | 替换 9 处 |
| `src/services/agent/resilience.ts` | 替换 2 处 |
| `src/services/agent/tools/getWeather.ts` | 替换 2 处 |
| `src/services/optimizeService.ts` | 替换 1 处 |
| `src/services/knowledgeService.ts` | 替换 11 处 |
| `src/services/queryRewriter.ts` | 替换 4 处 |
| `src/services/reranker.ts` | 替换 5 处 |
| `src/services/summaryService.ts` | 替换 4 处 |
| `src/services/tripService.ts` | 替换 6 处 |
| `src/services/userService.ts` | 替换 2 处 |
| `src/config/chroma.ts` | 替换 1 处 |
| `src/config/embeddings.ts` | 替换 4 处 |
| `src/utils/stream.ts` | 替换 3 处 |
| `.env` | + LOG_LEVEL / LOG_FILE |

总计 **16 个文件改动**，~200 行变更。

---

## 8. 未来可选优化（暂不实施）

### 8.1 OpenTelemetry 集成

```typescript
import { trace } from '@opentelemetry/api'
const span = trace.getActiveSpan()
log.info({ traceId: span?.spanContext().traceId }, '...')
```

Loki / Tempo 可关联日志 + 链路。

### 8.2 日志采样

生产环境流量大时可采样：
```typescript
const baseLogger = pino({
  level: process.env.LOG_LEVEL,
  sampling: { head: 100, tail: 100 },  // 头 100 + 尾 100 全记，中间 1/N
})
```

### 8.3 Loki 远程推送

```typescript
baseLogger = pino({}, pino.transport({
  target: 'pino-loki',
  options: { host: 'http://loki:3100', labels: { service: 'trip-server' } }
}))
```
