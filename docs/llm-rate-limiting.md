# LLM 限流方案

> 实施日期：2026-06-19
> 涉及文件：11 个（5 新 + 6 改）
> 相关：tasks/todo.md（LLM 限流方案优化计划章节）

## 背景与问题

原有限流方案只有 3 个 `express-rate-limit` 实例，覆盖 chat 20/min 和登录 10/15min，存在 6 个核心问题：

| 问题 | 说明 | 严重程度 |
|------|------|---------|
| 请求数 vs Token | 按请求数限流，但 ReAct Agent 一次请求最多触发 8+ 次 LLM 调用，Token 消耗差异巨大 | P0 |
| IP 限流 | 多用户 JWT 应用按 IP 限流，NAT 后互相挤占、移动网络可绕过 | P0 |
| 无并发控制 | SSE 长连接 10-60s，无并发限制会打爆 provider 并发额度 | P1 |
| 接口裸奔 | recommend / optimize / knowledge CRUD 无任何限流 | P0 |
| 零 Token 监控 | LangChain `usage_metadata` 从未读取，无法做 Token 级限流和成本核算 | P1 |
| 无全局兜底 | 单点漏限可打爆共享的 provider 额度 | P0 |

## 请求处理管线

```
请求 → authMiddleware
     → ①请求频率检查（per-user，超限 429）
     → ②Token 预算检查（per-user + global，超限 429）
     → ③并发获取（per-user 1 + global 10，超限 429）
     → ④执行 LLM 调用（callback 自动记录 token，扣减预算）
     → ⑤res.on('finish') 释放并发信号量
```

## 核心参数

| 参数 | 值 | 说明 |
|------|-----|------|
| /chat 请求频率 | 20/min | per-user |
| /recommend 请求频率 | 5/min | per-user |
| /optimize 请求频率 | 5/min | per-user |
| /knowledge/* 请求频率 | 100/min | per-user |
| 全局兜底 | 200/min | 全 API |
| per-user Token 预算 | 50,000 token/小时 | 保守起步 |
| global Token 预算 | 200,000 token/分钟 | 保护 provider TPM |
| per-user 并发 | 1 | 一个用户一次只能有一个 LLM 请求 in-flight |
| global 并发 | 10 | 同时最多 10 个 LLM 请求 |
| 超限响应 | 直接 429，不排队 | `{ code: 429, error: "..." }` |
| 存储后端 | 内存 | 接口预留，后续可迁 Redis |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│ Express Middleware Chain                                     │
│                                                              │
│  authMiddleware → rateLimit → tokenBudget → concurrencyGuard │
│                                         │                    │
│                                         ▼                    │
│                                  llmContext.run({userId})    │
│                                         │                    │
│                                         ▼                    │
│                               Controller / Service           │
│                                         │                    │
│                                         ▼                    │
│                               LLM Call (LangChain / raw)     │
│                                         │                    │
│                              ┌──────────┴──────────┐        │
│                              ▼                     ▼         │
│                     TokenTrackingCallback    recordFetch     │
│                     (onLLMEnd 自动捕获)     TokenUsage()      │
│                              │                     │         │
│                              ▼                     ▼         │
│                     tokenBudget.recordUsage()                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Event Lifecycle                                              │
│                                                              │
│  res.on('finish') ──► release() ▶ Semaphore.release()       │
│  res.on('close')  ──► release() ▶ (双重保障，幂等)          │
└─────────────────────────────────────────────────────────────┘
```

## 文件详解

### 新文件（5 个）

#### `middleware/rateLimiter.ts`
限流中间件工厂。包含：

- **`RateLimitStore`** 接口 — 定义 `increment(key, windowMs)` / `resetKey(key)` 方法
- **`MemoryStore`** — 内存实现，自动过期清理（60s 间隔），`unref` 不阻止进程退出
- **`createLimiter(config)`** — 返回 Express 中间件，keyGenerator 默认 `req.user.userId ?? req.ip`
- **`createTokenBudgetGuard()`** — Token 预算预检中间件，调用 `tokenBudget.checkUserBudget/checkGlobalBudget`

未登录请求回退到 IP 限流，已登录按 userId 限流，避免 NAT 问题。

#### `middleware/concurrencyGuard.ts`
并发控制中间件。包含：

- 全局 Semaphore（max=10）+ per-user Semaphore（max=1）
- 通过 `llmContext.run({ userId }, next)` 注入 AsyncLocalStorage 上下文，使下游所有 LLM 回调都能读取到当前 userId
- `res.on('finish')` + `res.on('close')` 双重释放保障，使用 `released` 标志确保幂等
- 环境变量：`LLM_GLOBAL_CONCURRENCY`（默认 10），`LLM_USER_CONCURRENCY`（默认 1）

#### `services/llmGuard/semaphore.ts`
信号量原语。包含：

- **`Semaphore`** 类 — `tryAcquire()` 返回 boolean（不等待），`release()`，`available` getter
- **`ConcurrencyGuard`** 类 — 管理 global + per-user 两层信号量。per-user 使用 ref count 追踪，空闲 60s 后自动清理

#### `services/llmGuard/tokenBudget.ts`
Token 预算管理。包含：

- **`TokenBudgetManager`** 类 — per-user 和 global 双窗口预算
- `checkUserBudget(userId)` / `checkGlobalBudget()` — 预检是否超限
- `recordUserUsage(userId, tokens)` / `recordGlobalUsage(tokens)` — 记录消耗
- 固定窗口策略：窗口到期自动重置
- 默认配置：per-user 50k/小时，global 200k/分钟

#### `services/llmGuard/tokenTracker.ts`
Token 追踪器。包含：

- **`llmContext`** — `AsyncLocalStorage<{ userId }>`，由 `concurrencyGuard` 注入
- **`TokenTrackingCallback`** — `BaseCallbackHandler` 子类，`onLLMEnd` 提取 `output.llmOutput.tokenUsage`，自动记录到 `tokenBudget`
- **`recordFetchTokenUsage(data)`** — 供 raw fetch 调用（如 queryRewriter）手动调用，解析 `data.usage.total_tokens`

#### `services/llmGuard/cache.ts`
通用缓存。包含：

- **`TTLCache<V>`** 类 — LRU 淘汰 + TTL 过期 + 自动清理
- `get(key)` / `set(key, value, ttlMs?)` / `getOrCompute(key, fn, ttlMs?)` / `invalidate(key)`
- **`recommendCache`** 单例 — maxSize=200，defaultTTL=1h

### 修改文件（6 个）

#### `config/llm.ts`
- 导入 `tokenTracker`
- `createLLM()` 和 `createLLMFromConfig()` 的 `ChatOpenAI` 构造函数增加 `callbacks: [tokenTracker]`
- 所有 LangChain LLM 调用自动追踪 Token

#### `services/queryRewriter.ts`
- 导入 `recordFetchTokenUsage`
- 在 `res.json()` 解析后调用 `recordFetchTokenUsage(data)`，提取 `data.usage.total_tokens`
- token 追踪失败不影响主流程（best-effort）

#### `services/tripService.ts`
- 导入 `recommendCache`
- `recommend()` 方法用 `recommendCache.getOrCompute(cacheKey, computeFn)` 包裹
- 缓存 key：`recommend:${city}:${budget}:${days}:${departureCity ?? 'none'}`
- 相同参数 1 小时内不重复调用 LLM

#### `routes/trip.routes.ts`
- 移除 `express-rate-limit`，改用自建 `createLimiter`
- 新增 recommend 5/min、optimize 5/min 限流
- 接入 `tokenBudgetGuard`（预检）和 `concurrencyGuard`（并发控制）
- 管线顺序：`auth → rateLimit → tokenBudget → concurrency → controller`

#### `routes/user.routes.ts`
- 移除 `express-rate-limit`，改用自建 `createLimiter`
- 逻辑不变（10/15min）

#### `routes/knowledge.routes.ts`
- 新增 `createLimiter({ max: 100 })` 全局应用到所有子路由

#### `index.ts`
- 新增全局兜底 `createLimiter({ max: 200 })` 作用在 `/api/*`

#### `middleware/idempotency.ts`
幂等中间件。包含：

- **`MemoryIdempotencyStore`** — 内存存储，TTL 过期自动清理
- **`createIdempotencyMiddleware()`** — 拦截 POST 请求，检查 `Idempotency-Key` header
- Key scope：`${userId}:${rawKey}`，不同用户同一 key 互不影响
- 流程：
  1. key 已缓存 → 直接返回缓存结果（跳过后续所有中间件）
  2. key 未缓存 → 劫持 `res.json()`，成功响应（2xx）自动缓存，正常执行
- TTL 默认 1 小时
- **仅影响 recommend 和 optimize**（非流式 POST 接口），chat 的 SSE 流不适合缓存

## 幂等性保障

### 防护矩阵（完整版）

| 防护层 | 用户连点 | 网关重试 | 客户端重试 | DB 重复 | LLM 重复 |
|--------|---------|---------|-----------|--------|---------|
| concurrencyGuard（per-user=1） | ✅ 同时拦截 | ✅ 处理中拦截 | ✅ 处理中拦截 | — | — |
| rateLimiter | ❌ 2-3 次超阈值前 | ❌ | ❌ | — | — |
| Idempotency Key | ✅ 窗口内全部拦截 | ✅ | ✅ | ✅ | ✅ |
| recommend 缓存 | ✅ 相同参数 | ✅ 相同参数 | ✅ 相同参数 | ✅ | ✅ |

### 最终中间件管线

```
chat:      auth → rateLimit → tokenBudget → concurrency → controller
recommend: auth → idempotency → rateLimit → tokenBudget → concurrency → controller
optimize:  auth → idempotency → rateLimit → tokenBudget → concurrency → controller

idempotency 在 rateLimit 之前：
  key 命中 → 直接返回，不消耗频率/Token/并发额度
  key 未命中 → 正常走后续管线，成功响应自动缓存
```

## LLM 调用点追踪覆盖

| 调用点 | 调用方式 | 追踪方式 | 状态 |
|--------|---------|---------|------|
| chat（ReAct 最多 8 轮） | LangChain | TokenTrackingCallback.onLLMEnd | ✅ |
| recommend（+JSON重试+fallback） | LangChain | TokenTrackingCallback.onLLMEnd | ✅ |
| optimize | LangChain | TokenTrackingCallback.onLLMEnd | ✅ |
| compressConversation（后台异步） | LangChain | TokenTrackingCallback.onLLMEnd | ✅（无 userId，仅记录 global） |
| rewriteQuery（RAG 工具内） | raw fetch | recordFetchTokenUsage(data) | ✅ |

## 超限响应

所有中间件超限后统一返回：

```json
{
  "code": 429,
  "error": "请求过于频繁，请稍后再试"
}
```

具体错误信息因中间件而异：
- 频率超限：`"对话请求过于频繁，请稍后再试"` 等（按端点区分）
- Token 超限：`"Token 额度已用尽，请稍后再试"`
- 并发超限：`"系统繁忙，请稍后再试"`

## 验证方式

```bash
# 编译检查
cd trip-server && npx tsc --noEmit

# 频率限流测试（recommend 5/min）
for i in {1..6}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"city":"成都","budget":3000,"days":3}' \
    http://localhost:3000/api/trip/recommend
done
# 期望：前 5 个 200，第 6 个 429

# 并发测试（同时发起 15 个请求）
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"hello"}' \
    http://localhost:3000/api/trip/chat &
done
wait
# 期望：10 个 200，5 个 429
```

## LLM 调用点 Token 消耗

（以下为单次调用的典型消耗，仅供参考）

| 调用点 | 输入 Token | 输出 Token | 合计 |
|--------|-----------|-----------|------|
| chat（1 轮 ReAct，无工具） | ~500 | ~200 | ~700 |
| chat（4 轮 ReAct + RAG 检索） | ~3,000 | ~1,000 | ~4,000 |
| recommend（含 JSON 约束） | ~1,000 | ~2,000 | ~3,000 |
| recommend（JSON 重试） | ~1,200 | ~2,000 | ~3,200 |
| optimize（含完整行程 JSON） | ~5,000 | ~2,000 | ~7,000 |
| compressConversation | ~3,000 | ~200 | ~3,200 |
| rewriteQuery | ~500 | ~50 | ~550 |

## 后续改进（待办）

1. **Idempotency Key** — 已实现。POST 请求传入 `Idempotency-Key` header，服务端缓存成功响应，窗口内相同 key 直接返回（scope=userId:key，TTL=1h）。适用于 recommend / optimize
2. **Redis 迁移** — `MemoryStore` / `TokenBudgetManager` 均定义了接口，可替换为 `rate-limit-redis` + Redis 计数器，支持多实例共享
3. **后台任务 userId 上下文** — `compressConversation` 目前无 userId 上下文，仅记录 global 用量。如需 per-user 统计，需传入 conversation 的 userId
4. **成本监控** — 当前 Token 数据仅用于限流，可扩展为定时落库，用于成本核算
5. **Sliding Window** — 当前使用固定窗口（窗口结束时计数重置），Sliding Window 更平滑，复杂度更高
6. **优先级队列（Phase 5）** — chat 高优先 / recommend 低优先 / 后台最低，适用于 provider 额度紧张时的降级
7. **环境变量显式化** — 当前默认值硬编码，后续可全部提取为环境变量文档化
