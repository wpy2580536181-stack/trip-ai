# Amap (高德) MCP 集成设计

> 目标：将 Amap MCP 工具集成到 trip-server 的 agent 系统中，作为 RAG 知识库的实时数据补充。
> 保留所有现有 RAG 工具，Agent（LLM）通过 Tool Calling 自主决定使用 Amap MCP 还是 RAG。

## 项目范围

本 spec 涵盖 **Amap MCP 集成**（本地 stdio + LLM 自主调用 + 完整护栏），不包含 Unsplash 图片功能（已 defer，MCP 完成后提醒）。

## 1. 架构总览

```
┌────────────────────────────────────────────────────────────┐
│ trip-server (Express + LangGraph)                          │
│                                                            │
│  ┌──────────────────┐    ┌─────────────────────────────┐  │
│  │  LLM Agent       │───→│  Tool Registry (7 工具)     │  │
│  │  (DeepSeek)      │    │  ┌────────────────────────┐ │  │
│  │  Tool Calling    │    │  │ RAG 工具 (保留, 3 个)   │ │  │
│  └──────────────────┘    │  │  - retrieve_knowledge   │ │  │
│                          │  │  - search_hotels        │ │  │
│                          │  │  - calculate_distance   │ │  │
│                          │  ├────────────────────────┤ │  │
│                          │  │ Amap MCP (新增, 4 个)   │ │  │
│                          │  │  - amap_search_poi      │ │  │
│                          │  │  - amap_weather         │ │  │
│                          │  │  - amap_route           │ │  │
│                          │  │  - amap_geocode         │ │  │
│                          │  └────────────────────────┘ │  │
│                          └──────────────────────────────┘  │
│                                    │                       │
│                                    ▼                       │
│                          ┌──────────────────────────────┐  │
│                          │  Amap MCP 护栏层 (新增)       │  │
│                          │  ┌─────────────────────────┐  │  │
│                          │  │ token-bucket 限流         │  │  │
│                          │  │ 3 QPS / tool              │  │  │
│                          │  │ 100 QPH / tool            │  │  │
│                          │  ├─────────────────────────┤  │  │
│                          │  │ opossum 断路器            │  │  │
│                          │  │ 10 次失败 → 10min Open    │  │  │
│                          │  ├─────────────────────────┤  │  │
│                          │  │ toolCache 30min TTL       │  │  │
│                          │  │ (city+tool_name key)      │  │  │
│                          │  ├─────────────────────────┤  │  │
│                          │  │ OTel span 埋点            │  │  │
│                          │  │ (耗时 / status / cache)   │  │  │
│                          │  └─────────────────────────┘  │  │
│                          └──────────────────────────────┘  │
│                                    │ stdio                │
│                                    ▼                       │
│                          ┌──────────────────────────────┐  │
│                          │  npx -y @amap/amap-maps-mcp   │  │
│                          │  (本地 stdio MCP server)      │  │
│                          │  env: AMAP_KEY               │  │
│                          └──────────────────────────────┘  │
│                                    │ HTTPS                 │
│                                    ▼                       │
│                          ┌──────────────────────────────┐  │
│                          │  高德开放平台 Web API         │  │
│                          └──────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 关键设计原则

- **不改 RAG 任何代码** — 双路并存，LLM 自主选择
- **Amap MCP 工具 = LangChain DynamicTool** — 内部经过护栏层后调用 stdio client
- **护栏失败 → DynamicTool 返回降级消息** — "Amap MCP 暂时不可用，请使用 RAG 知识库"，LLM 看到即走 RAG
- **高德 MCP server 进程** = `npx -y @amap/amap-maps-mcp-server` stdio 子进程，生命周期 = trip-server 进程

## 2. Agent 集成策略

- **决策方式**: LLM Tool Calling 自主决定（与现有 RAG 工具平铺到 tool list）
- **不再保留 `getWeather`（wttr.in）** — 由 `amap_weather` 替代（高德天气 API 实时性更高，且统一数据源）
- **保留 `calculate_distance`** — Haversine 公式做 `amap_route` 的 fallback（route 需要起止城市坐标，距离估算轻量级）
- **工具描述引导**：Amap 工具描述中强调"实时数据"以引导 LLM 优先使用

## 3. Amap MCP 工具详情

| 工具名 | 功能 | 参数 | 替换现有工具 |
|---|---|---|---|
| `amap_search_poi` | 搜索景点/酒店/餐饮/购物 POI | `keywords`, `city`, `types`(可选) | 补充 `retrieve_knowledge` |
| `amap_weather` | 实时天气 + 3 天预报 | `city`（支持中文/拼音） | **替代** `getWeather` (wttr.in) |
| `amap_route` | 真实路网路径规划 | `origin`, `destination`, `mode`(driving/walking/transit) | 补充 `calculate_distance` |
| `amap_geocode` | 地址→经纬度 | `address`, `city` | 新增 |

### 工具命名规范

- 前缀 `amap_` 与 RAG 工具区分
- 蛇形命名（与现有 `retrieve_knowledge` / `calculate_distance` 一致）
- 每个工具文件独立: `trip-server/src/services/agent/tools/amap*.ts`

## 4. 护栏层

### 4.1 token-bucket 限流

- 高德开放平台免费额度：5000 次/日（个人开发者），MCP 无额外限制
- **单工具限流**: 3 QPS, 100 QPH（远超安全余量）
- **实现**: `p-token` 库（in-memory, 单进程），分布式场景需换 Redis（本期不实现）
- 限流触发 → DynamicTool 返回 `"[Amap MCP 服务繁忙，请稍后重试或使用 RAG 知识库]"`

### 4.2 断路器

- **库**: `opossum`
- **触发条件**: 连续 10 次调用失败（超时/网络/高德服务错误）
- **熔断动作**: `Open` 状态 10 分钟，期间所有 Amap 调用直接返回降级消息
- **恢复**: 10 分钟后 `Half-Open`，发 1 次探测请求 → 成功则 `Closed`，失败则 `Open` 再 10 分钟
- **断路器阈值可调**: 初始设 10 次/10min，生产观察 1 周后调整

### 4.3 缓存

- **范围**: 仅缓存 `amap_weather` 和 `amap_geocode`（POI/Route 动态性强不缓存）
- **TTL**: 30 分钟
- **key**: `${toolName}:${JSON.stringify(sortedArgs)}`
- **复用** `toolCache` 现有逻辑（见 `trip-server/src/services/agent/toolCache.ts`）

### 4.4 OTel Tracing

- 每个 Amap MCP 调用起 `mcp.call.${toolName}` span
- 属性: `cache.hit`（布尔）、`circuit.state`（字符串）、`rate_limit.remaining`（数字）
- 成功 → span.setStatus({code: OK}); 失败 → span.setStatus({code: ERROR, message})

### 4.5 告警

- **mcp_down**: 断路器 Open → 立即发 webhook
- **mcp_degraded**: 1h 失败率 > 30% → 发告警
- **mcp_slow**: P99 > 5s → 发告警
- 复用 `src/config/alert.ts` 现有告警类型（新增 `mcp_down`, `mcp_degraded`, `mcp_slow` 3 种）

## 5. 降级策略

| 场景 | 行为 | 用户感知 |
|---|---|---|
| 单次瞬时失败（网络抖动） | 重试 1 次后返回降级消息 | LLM 多等 2-3s，走 RAG 回答 |
| 断路器 Open（10min） | 直接返回降级消息，不走 Amap | LLM 完全用 RAG |
| 断路器 Open + RAG 也空 | LLM 通用知识（与现在一致） | 和现有无 Amap 一致 |
| 进程崩溃（npx 挂了） | 自动重启（指数退避，最多 3 次/min） | 首次失败后降级 30s-1min |

## 6. stdio 进程管理

- **启动**: trip-server 进程启动时 `child_process.spawn('npx', ['-y', '@amap/amap-maps-mcp-server'], {stdio: 'pipe', env: {AMAP_KEY}})`
- **健康检查**: 每 30s 发一次 `tools/list` JSON-RPC 请求，超时 5s
- **崩溃重启**: 指数退避（1s → 2s → 4s → 8s → max 16s），最多 3 次/min
- **优雅关闭**: `SIGTERM` 时发子进程 `SIGTERM`，等待 5s 后 `SIGKILL`

## 7. 可观测性

- **Pino 日志**: 每次调用打 `logger.info({tool, duration, status, cache_hit, circuit_state}, 'amap mcp call')`
- **OTel Span**: 同上（4.4）
- **管理端路由**: `GET /api/admin/mcp-stats`（已认证）返回近 1h 调用统计：调用次数/成功数/失败数/平均耗时/断路器状态
- **tokenUsageLog**: 记录 Amap MCP 调用次数（高德免费，仅记次数不记费用）

## 8. 文件结构

### 新增（8 个文件）

```
trip-server/src/services/mcp/
├── amapMcpClient.ts          # stdio 客户端 (JSON-RPC 通信, 50 行)
├── amapMcpToolLoader.ts      # MCP 工具 schema → LangChain DynamicTool (80 行)
├── amapGuards.ts             # token-bucket + opossum 断路器 + 缓存 (120 行)
├── amapMcpProcess.ts         # stdio 进程管理 (启动/健康检查/重启) (60 行)
└── __tests__/
    └── amapMcpClient.test.ts # mock stdio, 测 JSON-RPC 解析 (200 行)

trip-server/src/services/agent/tools/
├── amapSearchPoi.ts          # amap_search_poi DynamicTool (20 行)
├── amapWeather.ts            # amap_weather DynamicTool (20 行, 替代 getWeather)
├── amapRoute.ts              # amap_route DynamicTool (20 行)
└── amapGeocode.ts            # amap_geocode DynamicTool (20 行)
```

### 修改（6 个文件）

```
trip-server/src/services/agent/tools/agentTools.ts    # 注册 4 个 Amap 工具
trip-server/src/services/agent/agentEngine.ts         # tool list 加 4 个 Amap 工具
trip-server/src/services/tokenUsageLog.ts             # 加 Amap 调用计数
trip-server/src/config/alert.ts                       # 加 mcp_down / mcp_degraded / mcp_slow
trip-server/.env.example                              # + AMAP_API_KEY
trip-server/package.json                              # + @modelcontextprotocol/sdk, opossum, p-token
```

### 删除（1 个文件）

```
trip-server/src/services/agent/tools/getWeather.ts   # 被 amap_weather 替代
```

## 9. 部署

1. 用户去高德开放平台 (https://lbs.amap.com/) 注册 → 创建 Web 服务应用 → 获取 API Key
2. `.env` 新增 `AMAP_API_KEY=your_key_here`
3. `npm install` 安装新依赖（`@modelcontextprotocol/sdk`, `opossum`, `p-token`）
4. `npm start` = trip-server 进程启动 → 自动 spawn npx Amap MCP 子进程
5. 无需 Docker 改动

## 10. 测试

| 层级 | 内容 | 文件 |
|---|---|---|
| 单元 | mock stdio, 测 JSON-RPC 请求/响应解析 | `amapMcpClient.test.ts` |
| 单元 | mock `toolCache` + fake timers, 测 token-bucket 拒绝 + 断路器状态切换 | `amapGuards.test.ts` |
| 集成 | mock amapMcpClient, 验证 tool list + 断路器 Open 时降级到 RAG | `agentEngine.test.ts` |
| Smoke | `npm run mcp:smoke` 调 1 次真实 amap_weather('北京')，校验返回结构 | `scripts/mcp-smoke.ts` |
| 评估 | 加 1 个 fixture 场景："用 Amap MCP 查北京实时天气并规划故宫路线" | eval fixtures |

## 11. 风险与缓解

| 风险 | 缓解 |
|---|---|
| **LLM 自主调用可能忽略 Amap 工具** | 工具描述强引导词（"实时数据"）；A/B 测试 |
| **npx 启动慢（3-5s）** | 启动 1 次 + 30s 健康检查；失败后自动重启 |
| **断路器 10 次阈值太敏感** | 初始设 10 次/10min，生产观察后调大 |
| **Amap MCP server beta 不稳定** | tool 名称/schema 集中 `amapMcpToolLoader.ts`，升级只改 1 个文件 |
| **AMAP_API_KEY 泄露** | `.env` 管理；`.gitignore` 已忽略 `.env` |

## 12. 后续（本期不做）

- **Unsplash 景点图片** — 已 defer，MCP 完成后提醒 🛎️
- **Redis token-bucket** — 多 worker 场景需换 Redis 共享限流
- **Amap MCP 断路器阈值自动调优** — ML 控制，过度设计
- **SSE 代理模式** — 当前单 stdio 够用，多 MCP server 时考虑 mcp-proxy

---

*审批后下一技能：writing-plans*
