# Trip 系统 — Python 后端迁移需求 PRD

> **文档状态**：草案 v1.0  
> **作者**：产品经理 许清楚（Xu）  
> **日期**：2026-07-10  
> **下游消费者**：架构师 高见远（系统设计）、开发团队  
> **上游输入**：主理人 齐活林 提供的现有代码库分析报告

---

## 1. 项目信息

| 字段 | 内容 |
|---|---|
| **语言** | 中文 |
| **项目名称** | `trip-backend`（Python 后端迁移版） |
| **项目类型** | 后端迁移重写（Node.js → Python） |
| **原始需求复述** | 基于现有 Node.js + Express + TypeScript 的旅行规划后端系统，使用 Python 完整重写后端，保持前端零改动对接，覆盖现有全部核心功能模块。 |

### 1.1 现有系统速览

| 维度 | 现状 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Naive UI（**不迁移**） |
| 后端 | Express 5 + TypeScript（**本次迁移对象**） |
| 数据库 | MySQL 8.0 + Prisma ORM + ChromaDB（向量） |
| AI | LangChain JS + LangGraph JS + DeepSeek API |
| 数据规模 | 30,791 条 POI，覆盖 153 城 |
| API 端点 | 30+ 个，9 个路由模块 |
| 数据表 | 9 张（roles/users/password_resets/trips/conversations/messages/spots/feedbacks/agent_steps） |

---

## 2. 产品目标

### 2.1 为什么要迁移到 Python？

本次迁移的核心驱动力并非现有 Node.js 系统存在不可接受的缺陷，而是出于**技术栈统一与生态红利**的战略考量：

| 目标 | 说明 |
|---|---|
| **G1：统一 AI 技术栈到 Python 生态** | Python 是 LLM/RAG/Agent 领域的事实标准语言。LangChain、LangGraph 的 Python 版本功能更完整、社区更活跃、文档更新更快（JS 版常滞后数月）。迁移后可直接使用 Python 生态的前沿工具（如 LangSmith 原生 SDK、LlamaIndex 互操作、Hugging Face `transformers` 原生支持），降低 AI 功能迭代的技术阻力。 |
| **G2：利用 Python 生态简化 AI 基础设施** | 现有项目通过 `@xenova/transformers`（JS 移植版）在本地运行 `bge-small-zh-v1.5` embedding 和 `bge-reranker-base` reranker，存在模型加载慢、版本受限等问题。Python 版可直接使用 `sentence-transformers` / `FlagEmbedding` 官方库，获得更好的模型兼容性和推理性能。 |
| **G3：保持功能与接口完全兼容** | 迁移是"后端重写"而非"产品重构"。前端零改动、API 契约完全兼容、数据模型一一映射是硬约束。迁移后的系统在功能、性能、可观测性上须达到或优于现有水平。 |

### 2.2 迁移成功后的目标状态

- ✅ 现有 Vue 3 前端无需任何代码改动，切换 `VITE_API_BASE` 指向 Python 后端即可正常工作
- ✅ 30+ 个 API 端点全部兼容，包括 SSE 流式对话的断点续传
- ✅ 9 张数据表结构与现有 MySQL 数据完全兼容（可直接复用现有数据库）
- ✅ RAG 检索、LangGraph 多智能体编排、MCP 集成等核心 AI 功能完整迁移
- ✅ 性能基线持平或优于现有 Node.js 版本

---

## 3. 迁移范围与边界

### 3.1 优先级划分

#### P0 — 必须迁移的核心功能（MVP 门槛）

| 模块 | 现有实现 | 迁移要点 |
|---|---|---|
| **用户认证** | JWT Bearer token，register/login/info/password/forgot/reset | JWT payload 格式 `{userId, username, roleId, exp}` 必须完全一致；bcrypt 密码哈希兼容 |
| **行程推荐** | `POST /api/trip/recommend`（同步），AI 生成行程 + RAG 检索 + LLM 调用 | 响应格式 `{success, data, error?}`；RAG 三路召回 + RRF + Cross-Encoder 重排 |
| **SSE 流式对话** | `POST /api/trip/chat`，fetch POST（非 EventSource） | **最高风险模块**：X-Stream-Id + Last-Event-ID 断点续传 + Redis 双写 + 5s 心跳 + 6 种事件类型 |
| **RAG 检索引擎** | 三路并行召回（Chroma 向量 + MySQL 关键词 + MySQL rating）+ RRF 融合 + Cross-Encoder 重排 | 向量检索用 ChromaDB Python client；Cross-Encoder 用 `sentence-transformers`；本地查询改写 |
| **LangGraph 多智能体** | ChatGraph（多轮对话）+ PlannerGraph（行程规划），5 节点 + 3 工具 | 迁移到 LangGraph Python 版；节点逻辑、状态图结构保持一致 |
| **对话与消息管理** | conversations/messages CRUD + 对话摘要压缩 | 分层摘要（"关键决策"+"对话脉络"）append 模式 |
| **行程历史** | trips 列表/详情/删除 | Prisma `_count` 嵌套字段需兼容 |
| **景点知识库** | spots CRUD（admin 写权限） | 全文检索（FULLTEXT 优先 LIKE 回退）需在 Python ORM 中实现 |
| **基础中间件** | 鉴权、CORS、限流、幂等性 | CORS 白名单一致；限流规则一致 |

#### P1 — 建议迁移的增强功能（完整度保障）

| 模块 | 现有实现 | 迁移要点 |
|---|---|---|
| **LLM 守卫** | Token 预算（用户 50K/h，全局 200K/min）+ 并发守卫（全局 10，单用户 1）+ 工具缓存 | 环形缓冲区 TokenMonitor；工具缓存（字面归一化 + embedding 归一化 cosine≥0.85） |
| **MCP 集成** | 高德地图 MCP（stdio JSON-RPC 子进程）+ opossum 熔断 + 令牌桶限流 + 缓存 | Python MCP client（stdio 子进程）；熔断可用 `pybreaker` 或自实现；30min 缓存 |
| **Agent 可观测性** | TraceRecorder（trace 落库）+ SpanTracker + MetricBoard + TokenMonitor | agent_steps 表写入；trace 查询 API |
| **反馈系统** | feedbacks 提交/统计/admin 分析/转 fixture | 在线评估（👍/👎 + tags） |
| **Token 用量统计** | stats/token-usage 统计/日志 | 用量日志 API |
| **JSON 鲁棒性** | 三级校验修复（repairJson → Zod → 业务逻辑） | Python 版 JSON 修复 + Pydantic 校验 |

#### P2 — 可暂缓迁移的次要功能（可后续迭代）

| 模块 | 现有实现 | 说明 |
|---|---|---|
| **告警系统** | node-cron 调度 + 满意率检测 + Redis 去重 + Webhook（飞书/Slack/钉钉/企微） | 非核心功能，可后期用 APScheduler 实现 |
| **DeepSeek prefix cache 优化** | system prompt 跨轮字节稳定化 | 微优化，可后期迭代 |
| **Cluster 多进程** | Primary fork ≤8 worker | Python 可用 uvicorn/gunicorn workers 替代 |
| **反馈转 fixture** | feedback-to-fixture 脚本 | 开发辅助工具，可后期迁移 |

#### 明确不迁移的部分

| 部分 | 原因 |
|---|---|
| **前端（trip-front）** | 迁移目标是后端，前端保持 Vue 3 原样 |
| **前端 API 模块** | 8 个 API 模块（user/request/conversation/history/feedback/knowledge/tokenUsage/trace）不改动 |
| **现有数据库数据** | 30,791 条 POI 数据直接复用，无需迁移数据 |
| **ChromaDB 向量数据** | 现有向量索引直接复用，Python 端连接同一 ChromaDB 实例 |
| **eval 评估框架** | 现有 vitest 评估脚本为 Node.js 专属，后续按需用 Python 重写 |

---

## 4. 用户故事

| # | 角色 | 故事 |
|---|---|---|
| US-1 | **前端开发者** | 作为前端开发者，我希望 Python 后端提供与现有后端完全兼容的 API 契约（响应格式、SSE 协议、鉴权、字段命名），这样前端代码无需任何改动即可切换到新后端。 |
| US-2 | **最终用户** | 作为旅行规划系统的用户，我希望迁移后系统功能完全一致——AI 行程生成、多轮对话、断点续传等体验无感知变化，不会因为后端语言切换而遇到功能缺失或性能下降。 |
| US-3 | **后端开发者** | 作为后端开发者，我希望 Python 后端利用 LangChain/LangGraph Python 生态的原生能力，这样我能更高效地迭代 AI 功能（如接入新的 embedding 模型、新的 reranker、LangSmith 追踪等），不再受 JS 版生态滞后制约。 |
| US-4 | **系统运维者** | 作为系统运维者，我希望 Python 后端的部署方式简洁（如 uvicorn + Docker），可观测性（日志、trace、指标）不弱于现有 pino + TraceRecorder 方案，这样运维体验不退化。 |
| US-5 | **项目作者** | 作为项目作者，我希望通过此次迁移深入学习 Python AI 生态（LangChain Python、sentence-transformers、async Python），同时产出一份可展示的"跨语言系统迁移"工程实践。 |

---

## 5. 兼容性要求（硬约束）

> 以下兼容性要求为**硬约束**，架构师设计时必须满足。任何不兼容都意味着前端需要改动，违反"零改动"目标。

### 5.1 双响应格式

现有后端存在**两套响应格式**，Python 后端必须逐接口精确匹配：

| 格式 | 适用接口 | 结构 |
|---|---|---|
| **格式 A** | `/api/trip/recommend` | `{ "success": bool, "data": ..., "error"?: str }` |
| **格式 B** | 其他所有接口 | `{ "code": 200, "data": ..., "message"?: str, "error"?: str }` |

### 5.2 SSE 流式协议（`/api/trip/chat`）

| 维度 | 要求 |
|---|---|
| **请求方式** | `POST /api/trip/chat`，fetch POST（**非** EventSource），因为需传 JSON body + Authorization header |
| **响应头** | `Content-Type: text/event-stream`；首次请求返回 `X-Stream-Id: <streamId>` |
| **SSE 事件格式** | `id: <seq>\ndata: <json>\n\n`，seq 为递增整数 |
| **事件类型**（json.type） | `chunk`（流式文本片段）、`complete`（结束）、`error`（错误）、`tool_start`（工具开始）、`tool_end`（工具结束）、`heartbeat`（5s 心跳） |
| **断点续传** | 重连时请求带 `X-Stream-Id` + `Last-Event-ID` 头，后端从该 seq 之后续传 |
| **complete 事件 data** | 必须含 `{ conversationId, usage: { prompt, completion, total } }` |
| **Redis 双写** | 每个 SSE 事件同步写入 Redis（HASH 存 streamId 状态 + LIST 存 events + STRING 存 seq），TTL 10 分钟 |
| **中止机制** | 客户端 AbortController 中止时，服务端需正确清理资源 |

### 5.3 鉴权

| 维度 | 要求 |
|---|---|
| **方式** | JWT Bearer token，`Authorization: Bearer <token>` |
| **payload** | `{ userId, username, roleId, exp }`，roleId=1 为 admin |
| **过期** | JWT_EXPIRES_IN=7d |
| **密码哈希** | bcrypt（必须与现有 Node.js `bcryptjs` 产生的哈希兼容，即同一 salt rounds） |
| **401 处理** | 返回 401 状态码，前端自动跳转登录 |
| **password_resets** | 找回密码 token 机制需兼容 |

### 5.4 字段命名

| 维度 | 要求 |
|---|---|
| **Prisma `_count`** | 列表接口需返回 `_count` 嵌套对象（如 `ConversationListItem._count.messages`）。Python ORM 无原生支持，需手动组装。 |
| **snake_case 映射** | 数据库字段为 snake_case（如 `created_at`），Prisma 自动映射为 camelCase（如 `createdAt`）。Python 后端须在序列化时做同样的 snake_case → camelCase 转换。 |
| **分页约定** | 统一 `{ items, total, page, pageSize }` |

### 5.5 CORS

| 维度 | 要求 |
|---|---|
| **白名单** | `localhost:5173`、`localhost:8080`、`localhost:3000`、`file://`（null origin） |
| **允许头** | `Content-Type, Authorization, X-Stream-Id, Last-Event-ID, x-request-id` |
| **开发代理** | Vite 将 `/api` 代理到 `http://localhost:3000`，Python 后端需监听同端口或调整代理 |

### 5.6 API 端点清单（完整迁移）

| 路由模块 | 端点 | 方法 |
|---|---|---|
| `/api/user` | register, login, info, password, forgot-password, reset-password | POST/GET/PUT |
| `/api/trip` | recommend（同步）, optimize（同步）, chat（**SSE 流式**） | POST |
| `/api/conversations` | 列表, 详情, 删除 | GET/DELETE |
| `/api/history/trips` | 列表, 详情, 删除 | GET/DELETE |
| `/api/knowledge/spots` | CRUD（admin 写） | GET/POST/PUT/DELETE |
| `/api/stats/token-usage` | 统计, 日志 | GET |
| `/api/feedback` | 提交, 统计, admin 分析, 转 fixture | POST/GET |
| `/api/admin/agent-trace` | trace 查询 | GET |
| `/api/admin/mcp-stats` | MCP 状态 | GET |

---

## 6. 非功能性需求

### 6.1 性能基线（须持平或优于）

> 以下为现有 Node.js 版本的实测指标，Python 版本须达到或优于。

| 指标 | 现有基线 | Python 目标 | 说明 |
|---|---|---|---|
| RAG 检索 P50 | ~640ms（Query Rewrite 300ms + 三路召回 200ms + RRF 1ms + Reranker 200ms） | ≤ 700ms | 允许小幅波动，但不能数量级退化 |
| 普通 API QPS（GET /api/history） | 6.67（10 并发） | ≥ 6.0 | 受 DB 限制，差距可接受 |
| SSE 流式 P99（10 并发） | 47.0s | ≤ 50s | 瓶颈在 DeepSeek 上游限流，非后端语言 |
| LLM /recommend P50 | 29.1s | ≤ 30s | 瓶颈在 LLM 推理，非后端语言 |
| LLM 缓存命中率 | 40.2% | ≥ 35% | 工具缓存逻辑需完整迁移 |
| 单流平均 chunk 数 | ~1000+ | 保持 | SSE 流式粒度不变 |

### 6.2 可观测性

| 维度 | 现有方案 | Python 目标 |
|---|---|---|
| **日志** | pino + pino-http（结构化 JSON 日志） | structlog / loguru（结构化 JSON） |
| **Agent Trace** | TraceRecorder → agent_steps 表 | 同表写入；trace 查询 API 兼容 |
| **Token 监控** | 环形缓冲区 + 阈值告警 | 等效实现 |
| **指标面板** | MetricBoard | 可用 prometheus-client 或等效方案 |

### 6.3 部署方式

| 维度 | 要求 |
|---|---|
| **运行时** | Python ≥ 3.12（异步生态成熟，性能优化到位） |
| **ASGI 服务器** | uvicorn（开发）+ gunicorn -k uvicorn.workers.UvicornWorker（生产多进程，替代 Node Cluster） |
| **容器化** | 提供 Dockerfile，支持 docker-compose 一键启动（Python 后端 + MySQL + ChromaDB + Redis） |
| **端口** | 默认 3000（与现有 Node.js 一致，前端代理无需改） |

### 6.4 可靠性

| 维度 | 现有方案 | 迁移要求 |
|---|---|---|
| **熔断降级** | opossum 熔断（Amap MCP / Chroma / Redis 三层降级） | Python 等效熔断（pybreaker 或自实现） |
| **限流** | express-rate-limit + 令牌桶 | slowapi / 自实现令牌桶 |
| **幂等性** | 幂等性中间件（Idempotency-Key） | 等效中间件 |
| **JSON 鲁棒性** | repairJson → Zod → 业务逻辑 | Python JSON 修复 + Pydantic 校验 |

---

## 7. 技术约束与偏好

### 7.1 技术栈方向性建议（供架构师参考，非最终决定）

| 层 | 现有技术（Node.js） | Python 候选 | 说明 |
|---|---|---|---|
| **Web 框架** | Express 5 | **FastAPI**（首选）/ Litestar | FastAPI 原生 async + SSE 支持 + Pydantic 校验，与现有 TypeScript 类型约束理念一致 |
| **ORM** | Prisma | **SQLAlchemy 2.0 + Alembic** / Tortoise ORM | SQLAlchemy 成熟稳定；需手动处理 `_count` 和 camelCase 序列化 |
| **AI 编排** | LangChain JS + LangGraph JS | **LangChain Python + LangGraph Python** | Python 版是官方主力，功能领先 |
| **向量数据库** | ChromaDB JS client | **ChromaDB Python client** | 连接同一 ChromaDB 实例，向量数据无需迁移 |
| **Embedding/Reranker** | @xenova/transformers（JS 移植版） | **sentence-transformers**（官方） | 原生支持 bge-small-zh-v1.5 / bge-reranker-base |
| **LLM 客户端** | @langchain/openai（DeepSeek 兼容 OpenAI 接口） | **langchain-openai Python** | 同样兼容 DeepSeek OpenAI 接口 |
| **Redis** | ioredis | **redis-py (async)** | 断点续传双写、缓存、限流 |
| **JWT** | jsonwebtoken | **PyJWT** | payload 格式必须一致 |
| **密码哈希** | bcryptjs | **bcrypt** (Python) | 需验证与现有哈希的兼容性 |
| **数据校验** | Zod | **Pydantic v2** | FastAPI 原生集成 |
| **日志** | pino | **structlog** / loguru | 结构化 JSON 日志 |
| **定时任务** | node-cron | **APScheduler** | 告警系统调度 |
| **熔断** | opossum | **pybreaker** / 自实现 | MCP 熔断 |
| **限流** | express-rate-limit | **slowapi** / 自实现 | API 限流 |

### 7.2 技术约束

- **Python 版本**：≥ 3.12（asyncio 性能、match-case、类型提示成熟度）
- **异步优先**：所有 I/O 密集模块（LLM 调用、DB、Redis、Chroma、SSE）必须使用 async/await
- **类型安全**：全量使用 type hints + Pydantic 模型，弥补动态语言的类型缺失
- **依赖管理**：推荐 `uv` 或 `poetry`，锁定依赖版本

---

## 8. 已确认决策

> 以下决策已由用户于 2026-07-03 确认，作为本项目的最终执行依据。

| # | 问题 | 选项 | 影响范围 | 决策 |
|---|---|---|---|---|
| Q1 | **是否保留 MySQL 还是迁移到 PostgreSQL？** | A) 保留 MySQL 8.0（数据零迁移）/ B) 迁移到 PostgreSQL（更好的全文检索 + JSON 支持） | ORM 选择、数据迁移工作量、FULLTEXT 索引实现 | ✅ **保留 MySQL 8.0**（数据零迁移，降低风险） |
| Q2 | **渐进式迁移还是一刀切？** | A) 一刀切（Python 后端完全替代 Node.js 后端）/ B) 渐进式（按路由模块逐步切换，Node.js 做反向代理） | 部署架构、开发计划、测试策略 | ✅ **一刀切**（Python 后端完全替代，前端切换 VITE_API_TARGET） |
| Q3 | **是否保留告警系统（P2）？** | A) 本次迁移包含 / B) 暂不迁移，后续迭代 | 开发工作量 | ✅ **暂不迁移**，后续迭代 |
| Q4 | **ORM 选择：SQLAlchemy 还是 Tortoise ORM？** | A) SQLAlchemy 2.0（功能全面，需手写 `_count` 和 camelCase）/ B) Tortoise ORM（Django 风格，更简洁但生态小） | 数据层架构、开发效率 | ✅ **SQLAlchemy 2.0** |
| Q5 | **Cross-Encoder 模型部署方式？** | A) 本地 sentence-transformers（现有方案）/ B) 切换为远程 API（如 Cohere Rerank） | 延迟、成本、依赖 | ✅ **本地 sentence-transformers**（与现有一致） |
| Q6 | **是否需要保留 eval 评估框架？** | A) 用 Python 重写评估脚本 / B) 保留 Node.js eval 脚本独立运行 | 测试基础设施 | ✅ **后期按需重写**，不阻塞迁移 |
| Q7 | **MCP 子进程通信方式是否调整？** | A) 保持 stdio JSON-RPC 子进程（现有方案）/ B) 切换为 SSE/HTTP MCP 传输 | MCP client 实现 | ✅ **保持 stdio JSON-RPC**（与高德 MCP server 兼容） |
| Q8 | **是否引入 LangSmith 追踪？** | A) 引入（Python 生态原生支持）/ B) 保持现有 TraceRecorder 方案 | 可观测性架构 | ✅ **可选启用**（通过环境变量开关，作为 Python 生态红利） |

---

## 9. 风险预判（供架构师参考）

| 风险 | 等级 | 说明 | 缓解策略 |
|---|---|---|---|
| **SSE 断点续传实现复杂度** | 🔴 高 | Redis 双写 + seq 管理 + Last-Event-ID 续传是现有系统最复杂的模块，Python ASGI 的 SSE 实现与 Express 有差异 | 优先实现并充分测试；编写专门的 SSE 续传集成测试 |
| **Prisma `_count` 兼容** | 🟡 中 | Python ORM 无 Prisma 的 `_count` 语法糖，需手动查询并组装嵌套对象 | 编写通用序列化工具函数，统一处理 `_count` |
| **bcrypt 跨语言兼容性** | 🟡 中 | Node.js `bcryptjs` 与 Python `bcrypt` 产生的哈希需互相验证 | 迁移前验证：用现有 Node.js 注册的账号在 Python 端登录 |
| **LangGraph Python 与 JS 版的 API 差异** | 🟡 中 | 两个语言的 LangGraph API 可能有细微差异（状态定义、工具声明方式） | 参照 LangGraph Python 官方文档逐节点迁移 |
| **camelCase 序列化** | 🟡 中 | 数据库 snake_case → API camelCase 的自动转换，Prisma 原生支持但 Python ORM 需手动处理 | 使用 Pydantic `alias_generator` 或自定义序列化器 |
| **ChromaDB client 差异** | 🟢 低 | Python client 与 JS client API 接近，且连接同一实例 | 风险低，快速验证 |

---

## 10. 验收标准

| # | 验收项 | 标准 |
|---|---|---|
| AC-1 | **前端零改动** | 现有 trip-front 代码不做任何修改，仅切换 API base URL 指向 Python 后端，所有功能正常 |
| AC-2 | **API 契约兼容** | 30+ 个 API 端点的响应格式、字段命名、状态码与现有后端完全一致（通过对比测试验证） |
| AC-3 | **SSE 流式对话** | 多轮对话、断点续传、心跳、中止、6 种事件类型全部正常工作 |
| AC-4 | **数据兼容** | Python 后端直连现有 MySQL 数据库，30,791 条 POI 数据正常读写 |
| AC-5 | **RAG 检索** | 三路召回 + RRF + Cross-Encoder 重排功能完整，检索结果质量与现有一致 |
| AC-6 | **LangGraph 编排** | ChatGraph 和 PlannerGraph 的多智能体流程正常，5 节点 + 3 工具完整迁移 |
| AC-7 | **性能基线** | RAG P50 ≤ 700ms，普通 API QPS ≥ 6.0，SSE P99 ≤ 50s |
| AC-8 | **鉴权兼容** | 现有 Node.js 注册的用户可在 Python 端正常登录，JWT token 互相兼容 |

---

> **下一步**：本 PRD 交付架构师高见远，由其进行 Python 后端的系统架构设计（框架选型、目录结构、API 设计、数据库映射、开发计划）。相关架构设计见 `migration-architecture.md`。

---

## 11. 执行计划

> 用户于 2026-07-03 确认以下执行计划，作为本项目的交付与协作依据。

### 11.1 代码组织方式

采用**同 repo 新目录**方案，在当前仓库主分支新建 `trip-backend/` 目录，与现有 `trip-server/` 并存开发。

**目录结构示意**：

```
trip/                              ← 仓库根目录（主分支）
├── trip-server/                   ← 现有 Node.js 后端（一行不改，开发期间照常运行）
│   └── src/...
├── trip-backend/                ← 新建 Python 后端（本次开发目标）
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── src/...
├── trip-front/                    ← 前端（不动）
└── docs/                          ← 文档（PRD + 架构设计在此）
```

**关键约定**：
- 现有 `trip-server/` 代码**一行都不改**，Python 代码在 `trip-backend/` 独立成长
- 主分支始终保持可用——开发期间 Node.js 后端照常跑，前端照常用
- **上线切换**：修改前端 `VITE_API_TARGET`，从 Node.js 端口（3000）切到 Python 端口（默认同样监听 3000，开发期可用 8000 避免冲突）
- **回滚方式**：把 `VITE_API_TARGET` 切回 Node.js 端口即可，零风险
- 迁移完成验证 OK 后，再决定是否删除 `trip-server/` 目录

### 11.2 交付节奏

采用**分阶段交付**，对应架构文档第 12 章的 6 个阶段（T01-T14）。每完成一个阶段，用户 review 一次，不一次性梭哈全部任务。

| 阶段 | 包含任务 | 预估工期 | 阶段交付物 |
|------|---------|---------|-----------|
| **阶段 1：骨架与基础设施** | T01 项目初始化与配置、T02 数据库模型与中间件 | 5 个工作日 | 可启动的 Python 项目骨架 + 9 张 SQLAlchemy 模型 + 中间件链 |
| **阶段 2：核心数据 CRUD** | T03 用户认证模块、T04 对话/行程/景点 CRUD | 5 个工作日 | 用户能登录注册 + 对话/行程/景点 CRUD 接口可用 |
| **阶段 3：AI 基础设施** | T05 RAG 检索引擎、T06 LangGraph+LLM 守卫+MCP、T07 行程推荐/优化、T08 对话摘要压缩 | 12 个工作日 | RAG 三路召回 + LangGraph 多智能体 + 行程推荐/优化接口可用 |
| **阶段 4：SSE 流式对话** | T09 SSE 流式对话（CRITICAL）、T10 SSE 断点续传测试 | 6 个工作日 | SSE 流式对话 + 断点续传 + 心跳 + 中止全部可用（最高风险模块） |
| **阶段 5：增强功能** | T11 反馈系统、T12 Token 统计+Agent Trace、T13 MCP 状态 API | 5 个工作日 | 反馈/Token 统计/Agent Trace/MCP 状态接口可用 |
| **阶段 6：集成测试与性能验证** | T14 API 对比测试 + 性能验证 | 3 个工作日 | 30+ 端点对比测试通过 + 性能基线达标 |

**预估总工期**：约 25 个工作日（5 周），不含阶段间的 review 间隔。

### 11.3 关键验证节点

以下节点为高风险模块的验证关卡，完成后立即跑兼容性验证，不等到最后：

| 节点 | 验证内容 | 验证方式 |
|------|---------|---------|
| **T02 完成后** | 数据库模型 + 中间件兼容性 | Python 后端连现有 MySQL，9 张表能正确读写；中间件链（鉴权/限流/CORS）行为与 Node.js 一致 |
| **T03 完成后** | 用户认证端到端验证 | 用现有 Node.js 注册的账号在 Python 端登录（bcrypt 兼容）；JWT token 互通；前端能完成登录注册流程 |
| **T09 完成后** | SSE 断点续传集成验证（最高风险） | 多轮对话 + 断点续传 + 心跳 + 中止 + 6 种事件类型；前端 Chat.vue 零改动能正常对话 |
| **T14 完成后** | 全量 API 对比 + 性能基线验证 | 30+ 端点响应格式与 Node.js 完全一致；RAG P50 ≤ 700ms；QPS ≥ 6.0；SSE P99 ≤ 50s |
