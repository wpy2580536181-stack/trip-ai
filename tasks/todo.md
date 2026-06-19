# Phase 3 实施计划

## 数据现状

`poi_raw/` 目录含 30 城市 JSON，格式为高德地图原始数据：
```json
{
  "city": "成都",
  "scenic": [{ "name": "金融城双子塔", "address": "...", "type": "风景名胜;公园", ... }],
  "food": [{ "name": "龙抄手", "address": "...", "type": "餐饮;中餐", ... }],
  "hotel": [{ "name": "锦江宾馆", "address": "...", "type": "住宿;酒店", ... }],
  "summary": "成都是四川省会..."
}
```

需转换为 Spot 格式：`{ name, city, category, description, tags, avgCost, duration, openTime, rating }`

---

## Task 1: POI 数据导入脚本

**目标：** 将 30 城市的 Amap 原始数据转换为知识库格式并批量导入。

**文件：**
- [ ] 修改 `trip-server/prisma/seed-knowledge.ts` — 支持从 `poi_raw/` 导入

**转换逻辑：**
- `scenic[*]` → `category: 'attraction'`
- `food[*]` → `category: 'food'`
- `hotel[*]` → `category: 'hotel'`
- 从 `type` 字段提取 tags（如 "风景名胜;公园广场;公园" → ["风景名胜","公园"]）
- description 用模板生成："{name}，位于{address}，类型{type}"
- avgCost/duration/openTime 留空（原始数据无此字段）

**预计导入量：** 30 城 × (3 scenic + 1 food + 1 hotel) ≈ 150 条

---

## Task 2: 知识库 CRUD API

**目标：** 提供管理员用的 spots 增删改查接口。

**文件：**
- [ ] 创建 `trip-server/src/controllers/knowledge.controller.ts`
- [ ] 创建 `trip-server/src/routes/knowledge.routes.ts`
- [ ] 修改 `trip-server/src/index.ts` — 注册路由

**接口：**
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/knowledge/spots` | 列表（支持 ?city=&category=&page=&pageSize=） | auth |
| GET | `/api/knowledge/spots/:id` | 详情 | auth |
| POST | `/api/knowledge/spots` | 新增 | admin |
| PUT | `/api/knowledge/spots/:id` | 更新 | admin |
| DELETE | `/api/knowledge/spots/:id` | 删除 | admin |
| POST | `/api/knowledge/spots/import` | 从 poi_raw/ 批量导入 | admin |

复用 `knowledgeService.listSpots`（已有）, 新增 `knowledgeService.updateSpot` / `deleteSpot`。

---

## Task 3: 知识库管理前端

**目标：** 管理员可查看和管理景点数据。

**文件：**
- [ ] 创建 `trip-front/src/views/KnowledgeManager.vue`
- [ ] 创建 `trip-front/src/api/knowledge.ts`
- [ ] 修改 `trip-front/src/router/index.ts` — 注册路由

**UI 设计：**
- 顶栏：城市下拉筛选 + 分类 tab + 搜索框
- 列表：van-cell 每行显示 名称 / 城市 / 分类 / 评分
- 操作：编辑（弹出表单）、删除（二次确认）
- 底部：批量导入按钮（调用 import 接口）
- 新增/编辑表单：name、city、category、description、tags、cost、rating 等字段

---

## 执行顺序

Task 1 → Task 2 → Task 3

## 自审

- 导入脚本复用现有 `bulkImportSpots`，自动同步 Chroma
- CRUD 接口写入后需同步 Chroma（更新时删旧向量加新向量）
- 前端管理页仅 admin 角色可见（路由 meta.requiresAdmin）

---

# LLM 限流方案优化计划

> 规划日期：2026-06-19
> 范围：trip-server（LLM 调用全链路限流）
> 决策来源：LLM API 专家视角分析 + 用户确认（P0-P4 一次性全做 / Token+并发双维度 / 内存先行预留 Redis / 保守阈值 / 直接 429）

## 背景

当前限流方案存在 6 个核心问题：
1. 按"请求数"限流，但 LLM 真实瓶颈是 Token 数 + 并发数（ReAct 一次请求最多触发 8+ 次 LLM 调用）
2. 按 IP 限流，但这是 JWT 多用户应用，应按 userId 限流
3. SSE 长连接无并发控制，可能耗尽 provider 并发额度
4. recommend / optimize 完全裸奔，无任何限流
5. 零 Token 监控，LangChain usage_metadata 完全未读取
6. 无全局兜底限流，单点漏限会打爆共享的 provider 额度

## 核心参数（已确认）

| 参数 | 值 | 说明 |
|------|-----|------|
| per-user 请求频率 | 各端点独立配置 | chat 20/min, recommend/optimize 5/min, knowledge 100/min |
| per-user Token 预算 | 50,000 token/小时 | 保守起步 |
| global Token 预算 | 200,000 token/分钟 | 保护 provider TPM |
| per-user 并发 | 1 | 一个用户同时只允许 1 个 LLM 请求 in-flight |
| global 并发 | 10 | DeepSeek 默认并发较低，10 安全 |
| 并发等待超时 | 不排队 | 直接 429 拒绝 |
| 超限响应 | 429 + 中文提示 | `{ code: 429, error: "..." }` |
| 存储后端 | 内存先行 | 定义 RateLimitStore / TokenBudgetStore 接口，预留 Redis 实现 |

## 请求处理管线

```
请求 → authMiddleware
     → ①请求频率检查（per-user，超限 429）
     → ②Token 预算检查（per-user + global，超限 429）
     → ③并发获取（per-user 1 + global 10，超限 429）
     → ④执行 LLM 调用（callback 自动记录 token，扣减预算）
     → ⑤res.on('finish') 释放并发信号量
```

## LLM 调用点清单

| 调用点 | 调用方式 | 文件 | Token 追踪 | 限流位置 |
|--------|---------|------|-----------|---------|
| chat（ReAct 最多 8 轮） | LangChain | agentEngine.ts | callback | HTTP 级 |
| recommend（+JSON重试+fallback） | LangChain | agentEngine.ts | callback | HTTP 级 |
| optimize | LangChain | optimizeService.ts:32 | callback | HTTP 级 |
| compressConversation（后台异步） | LangChain | summaryService.ts:26 | callback | 进程内 |
| rewriteQuery（RAG 工具内） | raw fetch | queryRewriter.ts:78 | 手动解析 | 在 agent 循环内 |

## 文件改动清单（5 新 + 6 改 = 11 个文件）

| # | 文件 | 类型 | 改动 |
|---|------|------|------|
| 1 | `trip-server/src/middleware/rateLimiter.ts` | NEW | RateLimitStore 接口 + MemoryStore + createLimiter() 工厂（key=userId??ip）+ createTokenBudgetGuard() |
| 2 | `trip-server/src/middleware/concurrencyGuard.ts` | NEW | tryAcquire() 信号量（per-user 1 + global 10），失败直接 429，res.on('finish') 释放 |
| 3 | `trip-server/src/services/llmGuard/tokenTracker.ts` | NEW | TokenTrackingCallback(LangChain) + wrapRawFetch() 包装 |
| 4 | `trip-server/src/services/llmGuard/tokenBudget.ts` | NEW | TokenBudgetStore + MemoryTokenBudget：checkBudget / recordUsage |
| 5 | `trip-server/src/services/llmGuard/cache.ts` | NEW | LRU+TTL 缓存，getOrCompute(key, ttl, fn) |
| 6 | `trip-server/src/config/llm.ts` | MODIFY | createLLM/createLLMFromConfig 注入 callbacks:[tokenTracker] |
| 7 | `trip-server/src/services/queryRewriter.ts` | MODIFY | fetch 用 wrapRawFetch() 包装，解析 data.usage.total_tokens |
| 8 | `trip-server/src/services/tripService.ts` | MODIFY | recommend() 加缓存（key=city+budget+days+departureCity, TTL=1h） |
| 9 | `trip-server/src/routes/trip.routes.ts` | MODIFY | 接入频率+并发+token 中间件 |
| 10 | `trip-server/src/routes/user.routes.ts` | MODIFY | 改用新工厂 |
| 11 | `trip-server/src/routes/knowledge.routes.ts` | MODIFY | 补限流 |
| (全局) | `trip-server/src/index.ts` | MODIFY | 全局兜底频率限流 |

## 分 Phase 实施

### Phase 1（P0）：补齐基础限流 + 存储抽象 + key 改造
- [ ] 新建 `middleware/rateLimiter.ts`：RateLimitStore 接口 + MemoryStore + createLimiter(config) 工厂
- [ ] `routes/trip.routes.ts`：recommend/optimize 加 5/min 限流，chat 改用新工厂
- [ ] `routes/knowledge.routes.ts`：加 100/min 限流
- [ ] `routes/user.routes.ts`：改用新工厂
- [ ] `index.ts`：加全局兜底 200/min

### Phase 2（P1）：并发控制
- [ ] 新建 `services/llmGuard/semaphore.ts`：Semaphore + ConcurrencyGuard
- [ ] 新建 `middleware/concurrencyGuard.ts`：per-user 1 + global 10 信号量中间件
- [ ] 接入 /chat /recommend /optimize 三个 LLM 接口

### Phase 3（P1）：Token 追踪 + 预算限流
- [ ] 新建 `services/llmGuard/tokenBudget.ts`：TokenBudgetStore + MemoryTokenBudget
- [ ] 新建 `services/llmGuard/tokenTracker.ts`：TokenTrackingCallback + wrapRawFetch()
- [ ] 修改 `config/llm.ts`：注入 callbacks
- [ ] 修改 `services/queryRewriter.ts`：用 wrapRawFetch 包装
- [ ] `middleware/rateLimiter.ts` 增 createTokenBudgetGuard()
- [ ] 接入三个 LLM 接口

### Phase 4（P2）：差异化配置 + recommend 缓存
- [ ] 新建 `services/llmGuard/cache.ts`：LRU+TTL
- [ ] 修改 `services/tripService.ts`：recommend() 加缓存
- [ ] 集中配置各端点限流参数表

### Phase 5（P3，可选）：优先级队列
- [ ] chat 高优先 / recommend+optimize 低 / 后台任务最低
- 可暂缓

## 差异化限流参数表（Phase 4 落地）

| 端点 | 请求频率 | 并发 | Token 权重 | 缓存 |
|------|---------|------|-----------|------|
| /chat | 20/min | 1 per user | 1x | 无 |
| /recommend | 5/min | 1 per user | 2x | 1h TTL |
| /optimize | 5/min | 1 per user | 2x | 无 |
| /knowledge/* | 100/min | 无 | 0 | 无 |

## 验证方式

- **编译**：`cd trip-server && npx tsc --noEmit`
- **lint**：`cd trip-server && npm run lint`（如有）
- **手动测试**：本地启动后用 curl 连打 recommend 验证 429；观察日志确认 token 追踪
- **并发测试**：同时发起 15 个 /chat 请求，验证 global=10 后的请求被拒

## 边缘情况

- 未登录用户（无 userId）回退到 IP 限流
- SSE 连接中断：concurrencyGuard 必须在 `res.on('close')` 也释放，避免泄漏信号量
- fallback LLM 切换后仍需追踪 token
- queryRewriter 失败已有兜底返回原 query，token 追踪失败不应影响主流程
- 进程重启后内存计数清零（Redis 阶段解决）

## 评审（待填写）

_实施完成后在此记录：实际改动文件数、是否如期完成、遇到的问题、与计划的偏差、性能数据_
