# Token 用量观测窗口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在前端独立页面 `/token-usage` 展示当前 token 窗口用量、进程启动以来累计、最近每次 LLM 调用的明细；个人 + 全局可切换（全局仅管理员）。

**Architecture:** 复用已有 `tokenBudget`（内存窗口计数）+ `tokenTracker`（LangChain/fetch 回调记账）。新增"进程生命周期累计"字段和内存环形缓冲明细日志（500 条），通过 `/api/stats/token-usage/{stats,logs}` 暴露，前端独立页面拉取展示。无 DB 持久化，进程重启清零（界面明确标注"自服务启动以来"）。

**Tech Stack:** Express + TypeScript（后端）；Vue 3 + Vant + axios（前端，`get(url, params)` 走 axios `{params}` 查询串，响应拦截器返回 body，运行时 body 为 `{ code, data, error }`，组件用 `any` 兜底——与 `user.ts` 一致）。

**测试策略:** 项目无测试框架（`test` script 为 echo）。AGENTS.md 仅对 bug 修复要求 TDD。本特性用 `tsc --noEmit`（后端）+ `vite build`（前端）+ 手动 curl 验证代替单元测试。

---

## File Structure

后端（7 个文件）：
- Modify: `trip-server/src/services/llmGuard/tokenBudget.ts` — 增加进程生命周期累计 + getGlobalStats/getUserStats
- Create: `trip-server/src/services/llmGuard/tokenUsageLog.ts` — 内存环形缓冲明细日志（500 条）
- Modify: `trip-server/src/services/llmGuard/tokenTracker.ts` — 记账时同时写明细；llmContext 类型加 endpoint
- Modify: `trip-server/src/middleware/concurrencyGuard.ts` — llmContext 注入 endpoint 短名
- Create: `trip-server/src/controllers/stats.controller.ts` — stats/logs 两个接口，global 需 roleId===1
- Create: `trip-server/src/routes/stats.routes.ts` — 挂在 `/api/stats`，带 authMiddleware
- Modify: `trip-server/src/index.ts` — 注册 statsRouter

前端（4 个文件）：
- Create: `trip-front/src/api/tokenUsage.ts` — 4 个 API 函数
- Create: `trip-front/src/views/TokenUsage.vue` — tabs 切换 + 进度条 + 明细列表
- Modify: `trip-front/src/router/index.ts` — 新增 `/token-usage` 路由
- Modify: `trip-front/src/views/Home.vue` — 快速操作 grid 加入口

---

## Task 1: tokenBudget 增加进程生命周期累计与查询方法

**Files:**
- Modify: `trip-server/src/services/llmGuard/tokenBudget.ts`

- [ ] **Step 1: 增加累计字段与统计方法**

在 `tokenBudget.ts` 中做如下改动：

(1) 在 `private globalData` 字段下方新增两个字段：

```typescript
  private globalTotalSinceStart = 0
  private userTotalSinceStart = new Map<string | number, number>()
```

(2) 在 `recordUserUsage` 方法内，`entry.total += tokens` 之后（即方法末尾前），新增累计：

将 `recordUserUsage` 改为：

```typescript
  async recordUserUsage(userId: string | number, tokens: number): Promise<void> {
    if (tokens <= 0) return
    const now = Date.now()
    let entry = this.userData.get(userId)
    if (!entry || now >= entry.resetAt) {
      entry = { total: tokens, resetAt: now + this.userWindowMs }
      this.userData.set(userId, entry)
    } else {
      entry.total += tokens
    }
    this.userTotalSinceStart.set(userId, (this.userTotalSinceStart.get(userId) ?? 0) + tokens)
  }
```

(3) 将 `recordGlobalUsage` 改为：

```typescript
  async recordGlobalUsage(tokens: number): Promise<void> {
    if (tokens <= 0) return
    const now = Date.now()
    if (now >= this.globalData.resetAt) {
      this.globalData = { total: tokens, resetAt: now + this.globalWindowMs }
    } else {
      this.globalData.total += tokens
    }
    this.globalTotalSinceStart += tokens
  }
```

(4) 在 `checkGlobalBudget` 方法之后，新增两个查询方法：

```typescript
  getGlobalStats(): { window: { current: number; limit: number; resetAt: number }; totalSinceStart: number } {
    const now = Date.now()
    let current: number
    let resetAt: number
    if (now >= this.globalData.resetAt) {
      current = 0
      resetAt = now + this.globalWindowMs
    } else {
      current = this.globalData.total
      resetAt = this.globalData.resetAt
    }
    return {
      window: { current, limit: this.globalLimit, resetAt },
      totalSinceStart: this.globalTotalSinceStart,
    }
  }

  getUserStats(userId: string | number): { window: { current: number; limit: number; resetAt: number }; totalSinceStart: number } {
    const now = Date.now()
    const entry = this.userData.get(userId)
    let current: number
    let resetAt: number
    if (!entry || now >= entry.resetAt) {
      current = 0
      resetAt = now + this.userWindowMs
    } else {
      current = entry.total
      resetAt = entry.resetAt
    }
    return {
      window: { current, limit: this.userLimit, resetAt },
      totalSinceStart: this.userTotalSinceStart.get(userId) ?? 0,
    }
  }
```

(5) 将 `shutdown` 方法改为同时清零累计：

```typescript
  shutdown(): void {
    clearInterval(this.cleanupTimer)
    this.userData.clear()
    this.globalData = { total: 0, resetAt: 0 }
    this.globalTotalSinceStart = 0
    this.userTotalSinceStart.clear()
  }
```

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit`（在 trip-server）
Expected: 通过（仅可能有 moduleResolution=node10 弃用告警，可忽略）

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/services/llmGuard/tokenBudget.ts
git commit -m "feat(token-budget): add totalSinceStart counters and getGlobalStats/getUserStats"
```

---

## Task 2: 新建 tokenUsageLog 环形缓冲

**Files:**
- Create: `trip-server/src/services/llmGuard/tokenUsageLog.ts`

- [ ] **Step 1: 写入文件**

```typescript
const DEFAULT_MAX_LOGS = 500

export interface TokenUsageLogEntry {
  userId: string | number
  endpoint: string
  tokens: number
  timestamp: number
}

export class TokenUsageLog {
  private logs: TokenUsageLogEntry[] = []
  private maxSize: number

  constructor(maxSize: number = DEFAULT_MAX_LOGS) {
    this.maxSize = maxSize
  }

  recordLog(entry: TokenUsageLogEntry): void {
    this.logs.push(entry)
    if (this.logs.length > this.maxSize) {
      this.logs.shift()
    }
  }

  getRecentLogs(opts?: { userId?: string | number; limit?: number }): TokenUsageLogEntry[] {
    const limit = opts?.limit ?? 50
    const filterUserId = opts?.userId
    let result = this.logs
    if (filterUserId !== undefined) {
      result = result.filter(l => l.userId === filterUserId)
    }
    return result.slice(-limit).reverse()
  }

  clear(): void {
    this.logs = []
  }

  size(): number {
    return this.logs.length
  }
}

export const tokenUsageLog = new TokenUsageLog()
```

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit`（在 trip-server）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/services/llmGuard/tokenUsageLog.ts
git commit -m "feat(token-log): add in-memory ring buffer for token usage logs"
```

---

## Task 3: tokenTracker 记账时写明细 + llmContext 加 endpoint

**Files:**
- Modify: `trip-server/src/services/llmGuard/tokenTracker.ts`

- [ ] **Step 1: 重写 tokenTracker.ts**

将整个文件替换为：

```typescript
import { AsyncLocalStorage } from 'async_hooks'
import { BaseCallbackHandler } from '@langchain/core/callbacks/base'
import type { LLMResult } from '@langchain/core/outputs'
import { tokenBudget } from './tokenBudget'
import { tokenUsageLog } from './tokenUsageLog'

export const llmContext = new AsyncLocalStorage<{ userId: string | number; endpoint?: string }>()

function recordUsage(tokens: number): void {
  const ctx = llmContext.getStore()
  const userId = ctx?.userId ?? 0
  const endpoint = ctx?.endpoint ?? 'background'
  tokenUsageLog.recordLog({ userId, endpoint, tokens, timestamp: Date.now() })
  if (ctx) {
    void tokenBudget.recordUserUsage(ctx.userId, tokens)
  }
  void tokenBudget.recordGlobalUsage(tokens)
}

export class TokenTrackingCallback extends BaseCallbackHandler {
  name = 'token_tracking'

  async onLLMEnd(output: LLMResult): Promise<void> {
    const tokenUsage = output.llmOutput?.tokenUsage
    if (!tokenUsage) return
    const total = (tokenUsage.totalTokens ?? 0) as number
    if (total <= 0) return
    recordUsage(total)
  }
}

export const tokenTracker = new TokenTrackingCallback()

export function recordFetchTokenUsage(data: { usage?: { total_tokens?: number } }): void {
  const total = data?.usage?.total_tokens
  if (!total || total <= 0) return
  recordUsage(total)
}
```

说明：
- `recordUsage` 同步先写日志，再用 `void` 触发 budget 记账（budget 方法体同步，`void` 仅忽略 Promise）。
- 后台任务无 ctx 时 endpoint=`'background'`、userId=0，仅计全局（与原逻辑一致：原代码 `if (ctx)` 才记 per-user）。
- `queryRewriter` 在 chat 请求上下文内运行，AsyncLocalStorage 自动透传 endpoint=`chat`，无需额外处理。

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit`（在 trip-server）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/services/llmGuard/tokenTracker.ts
git commit -m "feat(token-tracker): record usage logs and propagate endpoint via llmContext"
```

---

## Task 4: concurrencyGuard 注入 endpoint 短名

**Files:**
- Modify: `trip-server/src/middleware/concurrencyGuard.ts`

- [ ] **Step 1: 修改 llmContext.run 调用**

将 `concurrencyGuard.ts` 第 29 行：

```typescript
  llmContext.run({ userId }, next)
```

改为：

```typescript
  const endpoint = req.path.split('/').pop() || req.path
  llmContext.run({ userId, endpoint }, next)
```

说明：`req.path` 形如 `/api/trip/chat`，`split('/').pop()` 得 `chat`；`/trip/recommend` 得 `recommend`；`/trip/optimize` 得 `optimize`。

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit`（在 trip-server）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/middleware/concurrencyGuard.ts
git commit -m "feat(concurrency-guard): inject endpoint short name into llmContext"
```

---

## Task 5: 新建 stats controller

**Files:**
- Create: `trip-server/src/controllers/stats.controller.ts`

- [ ] **Step 1: 写入文件**

```typescript
import { Request, Response } from 'express'
import { tokenBudget } from '../services/llmGuard/tokenBudget'
import { tokenUsageLog } from '../services/llmGuard/tokenUsageLog'

export const getTokenUsageStats = (req: Request, res: Response): Response => {
  const scope = (req.query.scope as string) || 'user'
  if (scope === 'global') {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '权限不足' })
    }
    return res.json({ code: 200, data: tokenBudget.getGlobalStats() })
  }
  const userId = req.user?.userId ?? 0
  return res.json({ code: 200, data: tokenBudget.getUserStats(userId) })
}

export const getTokenUsageLogs = (req: Request, res: Response): Response => {
  const scope = (req.query.scope as string) || 'user'
  const limit = Math.min(Number(req.query.limit) || 50, 200)
  if (scope === 'global') {
    if (!req.user || req.user.roleId !== 1) {
      return res.status(403).json({ code: 403, error: '权限不足' })
    }
    return res.json({ code: 200, data: tokenUsageLog.getRecentLogs({ limit }) })
  }
  const userId = req.user?.userId ?? 0
  return res.json({ code: 200, data: tokenUsageLog.getRecentLogs({ userId, limit }) })
}
```

说明：非管理员传 `scope=global` → 403。`limit` 上限 200 防滥用。响应格式 `{ code, data }` 与项目一致。

- [ ] **Step 2: 类型检查**

Run: `npx tsc --noEmit`（在 trip-server）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/controllers/stats.controller.ts
git commit -m "feat(stats): add token usage stats and logs controllers"
```

---

## Task 6: 新建 stats routes 并注册

**Files:**
- Create: `trip-server/src/routes/stats.routes.ts`
- Modify: `trip-server/src/index.ts`

- [ ] **Step 1: 写入 stats.routes.ts**

```typescript
import { Router } from 'express'
import { authMiddleware } from '../middleware/auth'
import * as statsController from '../controllers/stats.controller'

const router = Router()
router.use(authMiddleware)
router.get('/token-usage/stats', statsController.getTokenUsageStats)
router.get('/token-usage/logs', statsController.getTokenUsageLogs)

export default router
```

- [ ] **Step 2: 在 index.ts 注册路由**

在 `trip-server/src/index.ts` 顶部 import 区，`knowledgeRouter` 行之后新增：

```typescript
import statsRouter from './routes/stats.routes'
```

在 `app.use('/api/knowledge', knowledgeRouter)` 之后新增：

```typescript
app.use('/api/stats', statsRouter)
```

- [ ] **Step 3: 类型检查**

Run: `npx tsc --noEmit`（在 trip-server）
Expected: 通过

- [ ] **Step 4: 后端整体验证**

启动后端：`npm run dev`（trip-server），确认无报错启动。
（如需 curl 验证可保留进程；下一步前端联调时一并测。）

- [ ] **Step 5: Commit**

```bash
git add trip-server/src/routes/stats.routes.ts trip-server/src/index.ts
git commit -m "feat(stats): mount /api/stats token-usage routes with auth"
```

---

## Task 7: 前端 tokenUsage API

**Files:**
- Create: `trip-front/src/api/tokenUsage.ts`

- [ ] **Step 1: 写入文件**

```typescript
import { get } from './request'

export interface TokenUsageWindow {
  current: number
  limit: number
  resetAt: number
}
export interface TokenUsageStats {
  window: TokenUsageWindow
  totalSinceStart: number
}
export interface TokenUsageLogEntry {
  userId: number | string
  endpoint: string
  tokens: number
  timestamp: number
}

export function getMyTokenStats() {
  return get('/stats/token-usage/stats', { scope: 'user' })
}

export function getGlobalTokenStats() {
  return get('/stats/token-usage/stats', { scope: 'global' })
}

export function getMyTokenLogs(limit = 50) {
  return get('/stats/token-usage/logs', { scope: 'user', limit })
}

export function getGlobalTokenLogs(limit = 50) {
  return get('/stats/token-usage/logs', { scope: 'global', limit })
}
```

说明：`get(url, params)` 第二参经 axios `{params}` 转查询串。响应拦截器返回 body（运行时 `{ code, data }`），组件侧用 `any` 兜底访问 `code`，与 `user.ts` 一致。

- [ ] **Step 2: 类型检查**

Run: `npx vite build`（在 trip-front）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add trip-front/src/api/tokenUsage.ts
git commit -m "feat(front): add tokenUsage api functions"
```

---

## Task 8: 前端 TokenUsage.vue 页面

**Files:**
- Create: `trip-front/src/views/TokenUsage.vue`

- [ ] **Step 1: 写入文件**

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { showToast } from 'vant'
import {
  getMyTokenStats,
  getGlobalTokenStats,
  getMyTokenLogs,
  getGlobalTokenLogs,
} from '@/api/tokenUsage'
import type { TokenUsageStats, TokenUsageLogEntry } from '@/api/tokenUsage'

const activeTab = ref<'user' | 'global'>('user')
const isAdmin = computed(() => {
  const stored = typeof window !== 'undefined' ? localStorage.getItem('userInfo') : null
  if (!stored) return false
  try {
    return JSON.parse(stored).roleId === 1
  } catch {
    return false
  }
})

const loading = ref(false)
const stats = ref<TokenUsageStats | null>(null)
const logs = ref<TokenUsageLogEntry[]>([])

const windowPercent = computed(() => {
  if (!stats.value) return 0
  const { current, limit } = stats.value.window
  return limit > 0 ? Math.min(100, Math.round((current / limit) * 100)) : 0
})

const resetInText = computed(() => {
  if (!stats.value) return ''
  const ms = stats.value.window.resetAt - Date.now()
  if (ms <= 0) return '即将重置'
  const mins = Math.floor(ms / 60000)
  if (mins > 0) return `${mins}分钟后重置`
  return `${Math.floor(ms / 1000)}秒后重置`
})

const fetchData = async () => {
  loading.value = true
  try {
    const scope = activeTab.value
    const statsReq = scope === 'global' ? getGlobalTokenStats() : getMyTokenStats()
    const logsReq = scope === 'global' ? getGlobalTokenLogs(50) : getMyTokenLogs(50)
    const [sRes, lRes]: any = await Promise.all([statsReq, logsReq])
    if (sRes?.code === 200) stats.value = sRes.data
    if (lRes?.code === 200) logs.value = lRes.data
  } catch {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
}

const onTabChange = () => {
  stats.value = null
  logs.value = []
  fetchData()
}

const formatTime = (ts: number) => {
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

const formatNum = (n: number) => n.toLocaleString('zh-CN')

const endpointLabels: Record<string, string> = {
  chat: '对话',
  recommend: '推荐',
  optimize: '优化',
  background: '后台任务',
}

onMounted(fetchData)
</script>

<template>
  <div class="page-container token-page">
    <div class="page-header">
      <van-nav-bar title="Token 用量" left-arrow @click-left="$router.back()">
        <template #right>
          <van-icon name="replay" size="20" @click="fetchData" />
        </template>
      </van-nav-bar>
    </div>

    <van-tabs v-model:active="activeTab" @change="onTabChange" sticky>
      <van-tab title="个人" name="user" />
      <van-tab v-if="isAdmin" title="全局" name="global" />
    </van-tabs>

    <div class="content">
      <div v-if="stats" class="stats-card">
        <div class="stat-row">
          <span class="label">窗口用量</span>
          <span class="value">{{ formatNum(stats.window.current) }} / {{ formatNum(stats.window.limit) }}</span>
        </div>
        <van-progress
          :percentage="windowPercent"
          :show-pivot="true"
          :color="windowPercent > 80 ? '#ee0a24' : '#1989fa'"
        />
        <div class="stat-row sub">
          <span class="label">窗口重置</span>
          <span class="value">{{ resetInText }}</span>
        </div>
        <div class="stat-row">
          <span class="label">自服务启动累计</span>
          <span class="value">{{ formatNum(stats.totalSinceStart) }}</span>
        </div>
      </div>

      <div class="logs-section">
        <div class="section-title">最近调用</div>
        <van-empty v-if="logs.length === 0" description="暂无调用记录" />
        <van-cell-group v-else inset>
          <van-cell v-for="(log, i) in logs" :key="i">
            <template #title>
              <div class="log-row">
                <span class="log-time">{{ formatTime(log.timestamp) }}</span>
                <span class="log-endpoint">{{ endpointLabels[log.endpoint] || log.endpoint }}</span>
                <span class="log-tokens">{{ formatNum(log.tokens) }}</span>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
        <div class="hint">仅展示最近调用记录，服务重启后清零</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.token-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f7f8fa;
}
.content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.stats-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}
.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}
.stat-row.sub {
  padding-top: 12px;
}
.stat-row .label {
  color: #666;
  font-size: 14px;
}
.stat-row .value {
  color: #333;
  font-size: 14px;
  font-weight: 500;
}
.section-title {
  font-size: 14px;
  color: #999;
  margin: 8px 4px;
}
.hint {
  text-align: center;
  color: #c8c9cc;
  font-size: 12px;
  margin-top: 12px;
}
.log-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.log-time {
  color: #999;
  font-size: 13px;
  min-width: 80px;
}
.log-endpoint {
  flex: 1;
  color: #333;
  font-size: 14px;
}
.log-tokens {
  color: #1989fa;
  font-size: 14px;
  font-weight: 500;
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `npx vite build`（在 trip-front）
Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add trip-front/src/views/TokenUsage.vue
git commit -m "feat(front): add TokenUsage view with tabs/progress/log list"
```

---

## Task 9: 注册路由 + Home 入口

**Files:**
- Modify: `trip-front/src/router/index.ts`
- Modify: `trip-front/src/views/Home.vue`

- [ ] **Step 1: router 新增路由**

在 `trip-front/src/router/index.ts` 的 `history` 路由之后，新增：

```typescript
  {
    path: '/token-usage',
    name: 'TokenUsage',
    component: () => import('../views/TokenUsage.vue'),
    meta: { requiresAuth: true },
  },
```

- [ ] **Step 2: Home.vue 快速操作加入口**

在 `trip-front/src/views/Home.vue` 的 `quick-actions` grid 内，`个人中心` grid-item 之后新增：

```html
        <van-grid-item icon="chart-trending-o" text="Token 用量" @click="$router.push('/token-usage')" />
```

（`van-grid` 已是 `:column-num="2"`，3 个 item 自动换行为 2 行，无需改列数。）

- [ ] **Step 3: 构建验证**

Run: `npx vite build`（在 trip-front）
Expected: 通过

- [ ] **Step 4: Commit**

```bash
git add trip-front/src/router/index.ts trip-front/src/views/Home.vue
git commit -m "feat(front): add /token-usage route and Home entry"
```

---

## Task 10: 端到端手动验证

- [ ] **Step 1: 启动后端**

Run: `npm run dev`（在 trip-server）
Expected: `Server is running on http://localhost:3000`，无报错。

- [ ] **Step 2: curl 验证 stats 接口（个人 scope）**

先登录拿 token（用现有用户账号替换 USERNAME/PASSWORD）：

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"USERNAME","password":"PASSWORD"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['token'])")
curl -s "http://localhost:3000/api/stats/token-usage/stats?scope=user" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `{"code":200,"data":{"window":{"current":0,"limit":50000,"resetAt":...},"totalSinceStart":0}}`

- [ ] **Step 3: curl 验证 logs 接口**

```bash
curl -s "http://localhost:3000/api/stats/token-usage/logs?scope=user&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `{"code":200,"data":[]}`（暂无调用记录）

- [ ] **Step 4: 触发一次 chat 调用后再次查询**

在前端发起一次对话（或直接 curl `/api/trip/chat` SSE），然后再次 Step 2 的 curl：
Expected: `current` 与 `totalSinceStart` 增长，logs 数组出现一条 `{endpoint:"chat",tokens:...,timestamp:...}`。

- [ ] **Step 5: 非管理员访问 global scope 应 403**

```bash
curl -s -o /dev/null -w "%{http_code}" "http://localhost:3000/api/stats/token-usage/stats?scope=global" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: 普通用户返回 `403`；管理员账号返回 `200`。

- [ ] **Step 6: 前端页面验证**

启动前端 `npm run dev`（trip-front），登录后：Home → 快速操作 → "Token 用量" → 进入页面，个人 tab 显示统计卡片与（可能为空的）明细列表；管理员可见全局 tab 并能切换。

---

## 边缘情况备忘

- `queryRewriter` 在 chat 请求的 AsyncLocalStorage 上下文内运行 → 明细 endpoint 自动归属 `chat`，无需额外处理。
- `compressConversation` 等后台任务无 ctx → endpoint=`background`、userId=0，仅计全局（与原 `if (ctx)` 逻辑一致）。
- 进程重启：`tokenBudget` 与 `tokenUsageLog` 全部内存数据清零 → 界面标注"自服务启动累计"与"服务重启后清零"。
- 环形缓冲 500 条：超出自动 `shift()` 丢最旧；`getRecentLogs` 取最后 N 条并 `reverse()` 使最新在前。
- 全局 rate limiter（`app.use('/api', createLimiter({max:200}))`）对 stats 接口生效，观测请求计入 200/min 全局配额——可接受。
- stats 接口带 `authMiddleware`，未登录返回 401。
