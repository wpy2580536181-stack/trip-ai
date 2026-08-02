# Trip 系统 — Python 后端迁移架构设计文档

> **文档状态**：v1.0  
> **作者**：架构师 高见远（Gao）  
> **日期**：2026-07-10  
> **上游输入**：迁移需求 PRD（许清楚）、现有 Node.js 代码库  
> **下游消费者**：开发团队（工程师按任务列表执行）

---

## 目录

1. [方案总览](#1-方案总览)
2. [系统架构设计](#2-系统架构设计)
3. [目录结构设计](#3-目录结构设计)
4. [数据库映射方案](#4-数据库映射方案critical)
5. [API 接口设计](#5-api-接口设计)
6. [SSE 流式对话实现方案](#6-sse-流式对话实现方案critical--最高风险模块)
7. [AI 编排层设计](#7-ai-编排层设计)
8. [鉴权与安全设计](#8-鉴权与安全设计)
9. [可观测性设计](#9-可观测性设计)
10. [部署架构](#10-部署架构)
11. [技术风险与解决策略](#11-技术风险与解决策略critical)
12. [任务分解与开发计划](#12-任务分解与开发计划critical)
13. [依赖包列表](#13-依赖包列表)
14. [共享知识（跨文件约定）](#14-共享知识跨文件约定)
15. [待明确事项](#15-待明确事项)

---

## 1. 方案总览

### 1.1 PRD 已确认决策

> 以下决策已由用户于 2026-07-03 确认，作为本架构设计的最终依据。

| # | 问题 | 已确认决策 | 理由 |
|---|---|---|---|
| **Q1** | MySQL 还是 PostgreSQL？ | ✅ **保留 MySQL 8.0** | 数据零迁移是硬约束。30,791 条 POI + 9 张表 + ChromaDB 向量数据全部复用。切 PostgreSQL 需要全量数据迁移 + 全文索引适配，风险高收益低。MySQL 的 JSON 类型和 FULLTEXT 索引已能满足当前需求。 |
| **Q2** | 渐进式还是一刀切？ | ✅ **一刀切** | 个人项目，前端零改动要求，且 Node.js 反向代理增加运维复杂度。一刀切可集中精力完成迁移，验收标准明确（前端切换 VITE_API_BASE 即可）。 |
| **Q3** | 是否保留告警系统（P2）？ | ✅ **暂不迁移** | 告警系统依赖 node-cron + Webhook 多平台集成，非核心功能。迁移后可用 APScheduler 后续迭代，不阻塞 MVP。 |
| **Q4** | SQLAlchemy 还是 Tortoise ORM？ | ✅ **SQLAlchemy 2.0** | SQLAlchemy 是 Python ORM 事实标准，生态最成熟，支持原生 SQL + FULLTEXT 查询、JSON 类型、异步引擎。Tortoise ORM 生态较小，复杂查询场景受限。 |
| **Q5** | Cross-Encoder 部署方式？ | ✅ **保持本地 sentence-transformers** | 与现有一致，延迟可控（~200ms），无额外 API 成本。Python 版直接使用 `BGE_reranker` 官方实现，比 JS 移植版 `@xenova/transformers` 性能更好。 |
| **Q6** | 是否保留 eval 评估框架？ | ✅ **后期按需重写** | 现有 vitest 评估脚本为 Node.js 专属。不阻塞迁移，后期可用 pytest + LangSmith 评估体系重写。 |
| **Q7** | MCP 通信方式是否调整？ | ✅ **保持 stdio JSON-RPC** | 高德 MCP server 为 stdio 模式，Python 端用 `asyncio.subprocess` 管理子进程，与现有 JS `child_process.spawn` 方案等价。 |
| **Q8** | 是否引入 LangSmith？ | ✅ **可选启用（环境变量开关）** | LangSmith 是 Python 生态原生支持的可观测性工具，作为 LangGraph 追踪的补充。通过环境变量 `LANGSMITH_API_KEY` 开关，不引入时降级为现有 TraceRecorder 方案。 |

### 1.2 最终技术栈选型

| 层 | 选型 | 版本约束 | 选型理由 |
|---|---|---|---|
| **Python 运行时** | CPython | ≥ 3.12 | asyncio 性能优化、match-case 语法、类型提示成熟 |
| **ASGI 框架** | FastAPI | ^0.111 | 原生 async + Pydantic v2 集成 + 自动 OpenAPI 文档 + StreamingResponse |
| **ORM** | SQLAlchemy 2.0 | ^2.0 | 声明式映射 + async session + 原生 SQL 支持 FULLTEXT |
| **数据库迁移** | Alembic | ^1.13 | SQLAlchemy 标配迁移工具；本次迁移**不执行 Alembic 迁移**（复用现有 Prisma 表结构），仅初始化空仓库备用 |
| **数据校验** | Pydantic v2 | ^2.7 | FastAPI 原生集成，`alias_generator` 实现 snake_case → camelCase |
| **AI 编排** | LangChain Python + LangGraph Python | langchain ^0.2, langgraph ^0.1 | Python 版是官方主力，功能领先 JS 版 |
| **LLM 客户端** | langchain-openai | ^0.1 | 兼容 DeepSeek OpenAI 接口 |
| **向量数据库** | ChromaDB Python client | ^0.5 | 连接同一 ChromaDB 实例，API 与 JS 版接近 |
| **Embedding/Reranker** | sentence-transformers | ^3.0 | 原生支持 bge-small-zh-v1.5 / bge-reranker-base |
| **Redis** | redis-py (async) | ^5.0 | async 支持、pipeline、连接池 |
| **JWT** | PyJWT | ^2.8 | payload 格式兼容 |
| **密码哈希** | bcrypt | ^4.1 | 与 Node.js bcryptjs 产生的 `$2a$`/`$2b$` 哈希兼容 |
| **日志** | structlog | ^24.1 | 结构化 JSON 日志，与 pino 输出格式对齐 |
| **熔断** | pybreaker | ^1.1 | MCP 熔断（替代 opossum） |
| **限流** | slowapi | ^0.1 | FastAPI 限流中间件（替代 express-rate-limit） |
| **HTTP 客户端** | httpx | ^0.27 | async HTTP，用于 Unsplash/高德 API 调用 |
| **定时任务** | APScheduler（P2，暂缓） | ^3.10 | 告警系统调度（后期迭代） |
| **依赖管理** | uv | latest | 极速依赖解析与锁定 |
| **ASGI 服务器** | uvicorn（开发）+ gunicorn -k uvicorn.workers.UvicornWorker（生产） | uvicorn ^0.30, gunicorn ^22 | 替代 Node Cluster 多进程 |

---

## 2. 系统架构设计

### 2.1 整体分层架构图

```mermaid
graph TB
    subgraph "接入层"
        CLIENT[Vue 3 前端]
        PROXY[Vite Dev Proxy /api → :3000]
    end

    subgraph "API 层"
        FA[FastAPI App]
        MW_AUTH[Auth 中间件]
        MW_CORS[CORS 中间件]
        MW_RATE[限流 slowapi]
        MW_IDEM[幂等性中间件]
        MW_CONCURRENCY[并发守卫]
        ROUTERS[9 个 APIRouter 分组]
    end

    subgraph "业务服务层"
        USER_SVC[UserService]
        TRIP_SVC[TripService]
        CONV_SVC[ConversationService]
        KNOW_SVC[KnowledgeService]
        FEED_SVC[FeedbackService]
        SUMMARY_SVC[SummaryService]
        OPT_SVC[OptimizeService]
        GEO_SVC[GeocodeService]
        IMG_SVC[ImageFetcher]
    end

    subgraph "AI 编排层"
        ENGINE[AgentEngine]
        CHAT_G[ChatGraph]
        PLANNER_G[PlannerGraph]
        NODES[5 节点: router/research/planner/chatPlanner/validate]
        TOOLS[3 工具: retrieveKnowledge/calculateDistance/searchHotels]
        RAG[RAG 引擎: 三路召回+RRF+Reranker]
        GUARD[LLM 守卫: TokenBudget/Concurrency/ToolCache]
        MCP[MCP Client: stdio JSON-RPC + 熔断 + 限流]
        SSE[SSE StreamManager: Redis双写+断点续传]
    end

    subgraph "数据层"
        DB[(MySQL 8.0)]
        REDIS[(Redis)]
        CHROMA[(ChromaDB)]
        MODELS[SQLAlchemy 2.0 Models]
    end

    subgraph "基础设施层"
        CONFIG[Settings pydantic-settings]
        LOG[structlog 日志]
        TRACE[TraceRecorder + agent_steps]
        TOKEN_MON[TokenMonitor 环形缓冲区]
    end

    CLIENT --> PROXY --> FA
    FA --> MW_CORS --> MW_RATE --> MW_AUTH --> MW_IDEM --> MW_CONCURRENCY --> ROUTERS
    ROUTERS --> USER_SVC & TRIP_SVC & CONV_SVC & KNOW_SVC & FEED_SVC
    TRIP_SVC --> ENGINE
    ENGINE --> CHAT_G & PLANNER_G
    CHAT_G & PLANNER_G --> NODES
    NODES --> TOOLS & RAG & MCP
    NODES --> SSE
    TOOLS --> RAG
    TRIP_SVC --> SSE
    USER_SVC & TRIP_SVC & CONV_SVC & KNOW_SVC & FEED_SVC --> MODELS --> DB
    SSE --> REDIS
    RAG --> CHROMA
    RAG --> MODELS
    ENGINE --> TRACE & TOKEN_MON
    CONFIG -.-> FA & MODELS & REDIS & CHROMA
    LOG -.-> FA & ENGINE & RAG & MCP
```

### 2.2 各层职责说明

| 层 | 职责 | 关键组件 |
|---|---|---|
| **接入层** | HTTP 请求接入、CORS、代理转发 | Vite dev proxy（开发）、Nginx（生产可选） |
| **API 层** | 路由分发、请求校验、中间件链、响应格式封装 | FastAPI App、9 个 APIRouter、6 个中间件 |
| **业务服务层** | 业务逻辑编排、数据 CRUD、事务管理 | 7 个 Service 类 |
| **AI 编排层** | LangGraph 多智能体编排、RAG 检索、LLM 守卫、MCP 集成、SSE 流式 | AgentEngine、ChatGraph/PlannerGraph、StreamManager |
| **数据层** | 数据持久化与访问 | SQLAlchemy 2.0 Models、MySQL、Redis、ChromaDB |
| **基础设施层** | 配置管理、日志、可观测性 | Settings、structlog、TraceRecorder、TokenMonitor |

### 2.3 与现有 Node.js 架构对照表

| 层 | Node.js（现有） | Python（迁移后） | 变化说明 |
|---|---|---|---|
| **Web 框架** | Express 5 | FastAPI | Express 中间件链 → FastAPI middleware + dependency injection |
| **路由** | express.Router × 9 | FastAPI APIRouter × 9 | 路由组织一致，挂载路径一致 |
| **控制器** | Controller 函数（req/res） | FastAPI 端点函数（依赖注入） | 从命令式 res.json 改为声明式 return + response model |
| **ORM** | Prisma Client | SQLAlchemy 2.0 async | Prisma `_count` → 手动查询组装；`@map` → SQLAlchemy `__tablename__` / `Column` name |
| **校验** | Zod | Pydantic v2 | Zod schema → Pydantic BaseModel |
| **AI 编排** | LangChain JS + LangGraph JS | LangChain Python + LangGraph Python | Annotation.Root → TypedDict；DynamicStructuredTool → @tool |
| **Embedding** | @xenova/transformers | sentence-transformers | pipeline('feature-extraction') → SentenceTransformer |
| **Reranker** | @xenova/transformers (CrossEncoder) | sentence-transformers CrossEncoder | 逻辑一致，Python 原生性能更优 |
| **Redis** | ioredis | redis-py async | API 接近，pipeline → redis-py pipeline |
| **JWT** | jsonwebtoken | PyJWT | payload `{userId, username, roleId, exp}` 完全一致 |
| **密码哈希** | bcryptjs (SALT_ROUNDS=12) | bcrypt (rounds=12) | `$2a$`/`$2b$` 格式兼容 |
| **日志** | pino + pino-http | structlog | 结构化 JSON 输出 |
| **熔断** | opossum | pybreaker | 熔断参数对齐 |
| **限流** | express-rate-limit | slowapi | 限流规则一致 |
| **Cluster** | node:cluster (fork) | gunicorn -k uvicorn.workers.UvicornWorker | 多进程管理 |
| **SSE** | Express res.write + 自定义 StreamManager | FastAPI StreamingResponse + async generator | 详见第 6 节 |
| **MCP** | child_process.spawn + readline | asyncio.subprocess + 异步读取 | stdio JSON-RPC 逻辑一致 |

---

## 3. 目录结构设计

### 3.1 Python 后端完整目录树

> **位置说明**：以下目录结构位于仓库根目录 `/Users/wang/Documents/trip/` 下的 `trip-backend/` 目录，与现有 `trip-server/`（Node.js）并存。开发期间 `trip-server/` 一行不改，`trip-backend/` 独立成长。详见 PRD 第 11.1 节"代码组织方式"。

```
trip-backend/                     ← 仓库根目录下的新目录
├── pyproject.toml                    # 依赖声明（uv/poetry）
├── .env.example                      # 环境变量模板
├── Dockerfile                        # 生产容器
├── docker-compose.yml                # 一键启动：Python + MySQL + ChromaDB + Redis
├── alembic.ini                       # Alembic 配置（本次不执行迁移，仅初始化）
├── alembic/
│   └── env.py
├── src/
│   ├── main.py                       # FastAPI 应用入口（等效 index.ts）
│   ├── app.py                        # create_app() 工厂函数（中间件链 + 路由挂载）
│   │
│   ├── config/                       # 配置层（等效 src/config/）
│   │   ├── __init__.py
│   │   ├── settings.py               # pydantic-settings 统一配置（合并所有 env 读取）
│   │   ├── database.py               # SQLAlchemy async engine + sessionmaker
│   │   ├── redis_client.py           # redis-py async 连接池 + is_redis_available()
│   │   ├── chroma_client.py          # ChromaDB Python client 单例
│   │   ├── embeddings.py             # sentence-transformers SentenceTransformer 单例
│   │   ├── llm.py                    # langchain-openai ChatOpenAI 工厂
│   │   ├── jwt_config.py             # JWT secret + 过期时间
│   │   └── amap.py                   # 高德 MCP 配置常量
│   │
│   ├── models/                       # SQLAlchemy 模型（等效 prisma/schema.prisma）
│   │   ├── __init__.py               # 导出所有模型
│   │   ├── base.py                   # DeclarativeBase + 公共 Mixin
│   │   ├── role.py                   # Role 模型 + RoleName 枚举
│   │   ├── user.py                   # User 模型
│   │   ├── password_reset.py         # PasswordReset 模型
│   │   ├── trip.py                   # Trip 模型（含自引用关系）
│   │   ├── conversation.py           # Conversation 模型
│   │   ├── message.py                # Message 模型
│   │   ├── spot.py                   # Spot 模型
│   │   ├── feedback.py               # Feedback 模型
│   │   └── agent_step.py             # AgentStep 模型
│   │
│   ├── schemas/                      # Pydantic 请求/响应模型（等效 Zod schemas）
│   │   ├── __init__.py
│   │   ├── common.py                 # 通用响应封装（格式A/B）、分页模型
│   │   ├── user.py                   # User 请求/响应 schema
│   │   ├── trip.py                   # Trip 请求/响应 schema
│   │   ├── conversation.py           # Conversation schema
│   │   ├── message.py                # Message schema
│   │   ├── spot.py                   # Spot schema
│   │   ├── feedback.py               # Feedback schema
│   │   ├── agent_step.py             # AgentStep schema
│   │   └── sse.py                    # SSE 事件 payload schema
│   │
│   ├── routers/                      # API 路由（等效 src/routes/）
│   │   ├── __init__.py
│   │   ├── user.py                   # /api/user/*
│   │   ├── trip.py                   # /api/trip/*（含 SSE chat）
│   │   ├── conversation.py           # /api/conversations/*
│   │   ├── history.py                # /api/history/trips/*
│   │   ├── knowledge.py              # /api/knowledge/spots/*
│   │   ├── stats.py                  # /api/stats/token-usage/*
│   │   ├── feedback.py               # /api/feedback/*
│   │   ├── trace.py                  # /api/admin/agent-trace/*
│   │   └── mcp.py                    # /api/admin/mcp-stats
│   │
│   ├── controllers/                  # 控制器（等效 src/controllers/）
│   │   ├── __init__.py
│   │   ├── user_controller.py
│   │   ├── trip_controller.py        # 含 SSE chat 端点逻辑
│   │   ├── conversation_controller.py
│   │   ├── history_controller.py
│   │   ├── knowledge_controller.py
│   │   ├── stats_controller.py
│   │   ├── feedback_controller.py
│   │   ├── trace_controller.py
│   │   └── mcp_controller.py
│   │
│   ├── services/                     # 业务服务层（等效 src/services/）
│   │   ├── __init__.py
│   │   ├── user_service.py           # 用户注册/登录/密码管理
│   │   ├── trip_service.py           # 行程推荐/聊天流
│   │   ├── conversation_service.py   # 对话管理 + _count 组装
│   │   ├── knowledge_service.py      # 景点 CRUD + RAG 检索
│   │   ├── feedback_service.py       # 反馈管理
│   │   ├── summary_service.py        # 对话摘要压缩
│   │   ├── optimize_service.py       # 行程优化
│   │   ├── geocode_service.py        # 高德地理编码
│   │   ├── trace_service.py          # Trace 查询服务
│   │   ├── fixture_converter.py      # Feedback → Fixture 转换（P2）
│   │   │
│   │   ├── agent/                    # AI 编排（等效 src/services/agent/）
│   │   │   ├── __init__.py
│   │   │   ├── agent_engine.py       # AgentEngine 单例
│   │   │   ├── chat_graph.py         # ChatGraph 状态图
│   │   │   ├── planner_graph.py      # PlannerGraph 状态图
│   │   │   ├── state.py              # PlannerState TypedDict
│   │   │   ├── types.py              # ResearchBundle, PlannerConfig
│   │   │   ├── system_prompt.py      # 系统提示词构建
│   │   │   ├── planner_prompt.py     # 规划提示词
│   │   │   ├── resilience.py         # 工具韧性包装（超时+重试+降级）
│   │   │   ├── tool_cache_wrapper.py # 工具缓存装饰器
│   │   │   ├── trace_recorder.py     # TraceRecorder + SpanTracker
│   │   │   │
│   │   │   ├── nodes/                # 5 个节点
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py         # 路由节点
│   │   │   │   ├── research.py       # 情报检索节点
│   │   │   │   ├── planner.py        # 行程规划节点
│   │   │   │   ├── chat_planner.py   # 聊天规划节点
│   │   │   │   └── validate.py       # JSON 校验修复节点
│   │   │   │
│   │   │   ├── tools/                # 3 个工具
│   │   │   │   ├── __init__.py
│   │   │   │   ├── retrieve_knowledge.py
│   │   │   │   ├── calculate_distance.py
│   │   │   │   └── search_hotels.py
│   │   │   │
│   │   │   └── observability/
│   │   │       ├── __init__.py
│   │   │       └── token_monitor.py  # TokenMonitor 环形缓冲区
│   │   │
│   │   ├── rag/                      # RAG 检索引擎（拆分自 knowledge_service）
│   │   │   ├── __init__.py
│   │   │   ├── query_rewriter.py     # 本地查询改写
│   │   │   ├── reranker.py           # Cross-Encoder 重排
│   │   │   └── rrf.py                # RRF 融合算法
│   │   │
│   │   ├── llm_guard/                # LLM 守卫（等效 src/services/llmGuard/）
│   │   │   ├── __init__.py
│   │   │   ├── token_budget.py       # TokenBudgetManager
│   │   │   ├── semaphore.py          # 并发守卫（asyncio.Semaphore）
│   │   │   ├── tool_cache.py         # ToolCache（字面+embedding 归一化）
│   │   │   ├── cache.py              # TTLCache + CacheAdapter
│   │   │   ├── redis_cache.py        # RedisTTLCache
│   │   │   ├── token_tracker.py      # LangChain callback handler
│   │   │   └── token_usage_log.py    # 用量日志
│   │   │
│   │   ├── mcp/                      # MCP 集成（等效 src/services/mcp/）
│   │   │   ├── __init__.py
│   │   │   ├── amap_process.py       # 子进程管理（asyncio.subprocess）
│   │   │   ├── amap_client.py        # JSON-RPC client
│   │   │   ├── amap_guards.py        # 熔断 + 限流 + 缓存
│   │   │   └── amap_tool_loader.py   # 动态加载 MCP tools 为 LangChain tools
│   │   │
│   │   ├── sse/                      # SSE 流式管理（等效 utils/stream.ts + streamStore.ts）
│   │   │   ├── __init__.py
│   │   │   ├── stream_store.py       # Redis 双写（HASH + LIST + STRING）
│   │   │   ├── stream_manager.py     # create_resumable_stream / resume_stream
│   │   │   └── errors.py             # StreamNotFoundError 等异常类
│   │   │
│   │   └── unsplash/                 # Unsplash 图片获取
│   │       ├── __init__.py
│   │       ├── unsplash_client.py
│   │       ├── unsplash_cache.py
│   │       └── image_fetcher.py
│   │
│   ├── middleware/                   # 中间件（等效 src/middleware/）
│   │   ├── __init__.py
│   │   ├── auth.py                   # JWT 鉴权 Depends
│   │   ├── cors.py                   # CORS 中间件
│   │   ├── rate_limiter.py           # slowapi 限流
│   │   ├── idempotency.py            # 幂等性中间件
│   │   ├── concurrency_guard.py      # 并发守卫 Depends
│   │   ├── token_budget_guard.py     # Token 预算守卫 Depends
│   │   └── request_id.py             # x-request-id 注入
│   │
│   ├── utils/                        # 工具函数（等效 src/utils/）
│   │   ├── __init__.py
│   │   ├── logger.py                 # structlog 配置 + 命名 logger
│   │   ├── params.py                 # 参数解析工具
│   │   ├── tokens.py                 # token 估算
│   │   ├── json_extractor.py         # JSON 修复提取
│   │   └── serialization.py          # _count 组装 + camelCase 序列化
│   │
│   └── exceptions.py                 # 全局异常定义 + handler
│
└── tests/                            # 测试
    ├── conftest.py                   # pytest fixtures
    ├── test_sse/                     # SSE 断点续传集成测试（重点）
    ├── test_api/                     # API 端点对比测试
    ├── test_rag/                     # RAG 检索测试
    └── test_agent/                   # LangGraph 编排测试
```

### 3.2 与现有目录的映射对照表

| Node.js 路径 | Python 路径 | 说明 |
|---|---|---|
| `src/index.ts` | `src/main.py` + `src/app.py` | 拆分为入口和工厂函数 |
| `src/config/*.ts` | `src/config/*.py` | 一一对应 |
| `prisma/schema.prisma` | `src/models/*.py` | Prisma schema → SQLAlchemy models |
| `src/routes/*.routes.ts` | `src/routers/*.py` | express.Router → APIRouter |
| `src/controllers/*.controller.ts` | `src/controllers/*.py` | 逻辑一致，改用 FastAPI 依赖注入 |
| `src/services/*.ts` | `src/services/*.py` | 一一对应 |
| `src/services/agent/` | `src/services/agent/` | 结构完全对应 |
| `src/services/rag/` (内嵌 knowledge) | `src/services/rag/` | 拆分为独立模块 |
| `src/services/llmGuard/` | `src/services/llm_guard/` | 命名风格转换 |
| `src/services/mcp/` | `src/services/mcp/` | 一一对应 |
| `src/services/streamStore.ts` | `src/services/sse/stream_store.py` | 重组到 sse 子包 |
| `src/utils/stream.ts` | `src/services/sse/stream_manager.py` | 重组到 sse 子包 |
| `src/middleware/` | `src/middleware/` | 一一对应 |
| `src/utils/` | `src/utils/` | 一一对应 |
| `src/types/agent.ts` | `src/schemas/` + `src/services/agent/types.py` | 类型定义分散到 Pydantic schema 和 agent types |

---

## 4. 数据库映射方案（CRITICAL）

### 4.1 Prisma → SQLAlchemy 2.0 完整映射

#### 4.1.1 基类与公共 Mixin

```python
# src/models/base.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func
from datetime import datetime

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    """对应 Prisma @default(now()) 的 createdAt"""
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime, server_default=func.now()
    )

class UpdatedAtMixin:
    """对应 Prisma @updatedAt 的 updatedAt"""
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at", DateTime, server_default=func.now(), onupdate=func.now()
    )
```

#### 4.1.2 Role 模型（含枚举）

```python
# src/models/role.py
import enum
from sqlalchemy import String, Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin

class RoleName(enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class Role(Base, TimestampMixin):
    __tablename__ = "roles"  # 对应 Prisma @@map("roles")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[RoleName] = mapped_column(
        Enum(RoleName, name="RoleName"), unique=True
    )  # 对应 Prisma enum RoleName @unique

    users: Mapped[list["User"]] = relationship(back_populates="role")
```

#### 4.1.3 User 模型

```python
# src/models/user.py
from sqlalchemy import String, Integer, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from datetime import datetime
from .base import Base, TimestampMixin, UpdatedAtMixin

class User(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "users"  # @@map("users")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)          # @db.VarChar(50)
    email: Mapped[str] = mapped_column(String(100), unique=True)            # @db.VarChar(100)
    password: Mapped[str] = mapped_column(String(255))                       # @db.VarChar(255)
    nickname: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role_id: Mapped[int] = mapped_column("role_id", Integer, ForeignKey("roles.id"), default=2)  # @map("role_id")
    status: Mapped[int] = mapped_column(Integer, default=1)                  # @map("status")
    preferences: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # Json?

    role: Mapped["Role"] = relationship(back_populates="users")
    trips: Mapped[list["Trip"]] = relationship(back_populates="user")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="user")
```

#### 4.1.4 PasswordReset 模型

```python
# src/models/password_reset.py
from sqlalchemy import String, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from datetime import datetime
from .base import Base, TimestampMixin

class PasswordReset(Base, TimestampMixin):
    __tablename__ = "password_resets"  # @@map("password_resets")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(100))
    token: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column("expires_at", DateTime)  # @map("expires_at")
    used: Mapped[bool] = mapped_column(Boolean, default=False)
```

#### 4.1.5 Trip 模型（含自引用关系）

```python
# src/models/trip.py
from sqlalchemy import String, Integer, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from .base import Base, TimestampMixin

class Trip(Base, TimestampMixin):
    __tablename__ = "trips"  # @@map("trips")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column("user_id", Integer, ForeignKey("users.id"), index=True)  # @map("user_id") + @@index([userId])
    from_city: Mapped[Optional[str]] = mapped_column("from_city", String(50), nullable=True)  # @map("from_city")
    city: Mapped[str] = mapped_column(String(50))
    days: Mapped[int] = mapped_column(Integer)
    budget: Mapped[int] = mapped_column(Integer)
    content: Mapped[Any] = mapped_column(JSON)  # Json (必填)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    parent_trip_id: Mapped[Optional[int]] = mapped_column(
        "parent_trip_id", Integer, ForeignKey("trips.id"), nullable=True
    )  # @map("parent_trip_id") 自引用

    user: Mapped[Optional["User"]] = relationship(back_populates="trips")
    parent: Mapped[Optional["Trip"]] = relationship(
        "Trip", remote_side="Trip.id", back_populates="versions",
        foreign_keys=[parent_trip_id]
    )
    versions: Mapped[list["Trip"]] = relationship(
        "Trip", back_populates="parent", foreign_keys=[parent_trip_id]
    )
```

#### 4.1.6 Conversation 模型

```python
# src/models/conversation.py
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import datetime
from .base import Base, TimestampMixin, UpdatedAtMixin

class Conversation(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "conversations"  # @@map("conversations")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column("user_id", Integer, ForeignKey("users.id"), index=True)  # @@index([userId])
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)        # @db.Text
    recap: Mapped[Optional[str]] = mapped_column(Text, nullable=True)          # @db.Text
    summary_error: Mapped[Optional[bool]] = mapped_column("summary_error", Boolean, default=False)
    summary_at: Mapped[Optional[datetime]] = mapped_column("summary_at", DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
```

#### 4.1.7 Message 模型（级联删除）

```python
# src/models/message.py
from sqlalchemy import String, Integer, Boolean, JSON, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from .base import Base, TimestampMixin

class Message(Base, TimestampMixin):
    __tablename__ = "messages"  # @@map("messages")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        "conversation_id", Integer, ForeignKey("conversations.id", ondelete="CASCADE")
    )  # onDelete: Cascade
    role: Mapped[str] = mapped_column(String(20))         # @db.VarChar(20)
    content: Mapped[str] = mapped_column(Text)             # @db.Text
    metadata_: Mapped[Optional[Any]] = mapped_column("metadata", JSON, nullable=True)
    excluded_from_context: Mapped[Optional[bool]] = mapped_column(
        "excluded_from_context", Boolean, default=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    feedbacks: Mapped[list["Feedback"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_messages_conv_created", "conversation_id", "created_at"),         # @@index([conversationId, createdAt])
        Index("idx_messages_conv_excluded", "conversation_id", "excluded_from_context"),  # @@index([conversationId, excludedFromContext])
    )
```

#### 4.1.8 Spot 模型

```python
# src/models/spot.py
from sqlalchemy import String, Integer, Float, JSON, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from .base import Base, TimestampMixin, UpdatedAtMixin

class Spot(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "spots"  # @@map("spots")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)        # @db.Text
    tags: Mapped[Any] = mapped_column(JSON)                # Json (必填)
    avg_cost: Mapped[Optional[float]] = mapped_column("avg_cost", Float, nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    open_time: Mapped[Optional[str]] = mapped_column("open_time", String(100), nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vector_id: Mapped[Optional[str]] = mapped_column("vector_id", String(100), unique=True, nullable=True)

    __table_args__ = (
        Index("idx_spots_city_category", "city", "category"),  # @@index([city, category])
    )
```

#### 4.1.9 Feedback 模型

```python
# src/models/feedback.py
from sqlalchemy import String, Integer, JSON, ForeignKey, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from .base import Base, TimestampMixin, UpdatedAtMixin

class Feedback(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "feedbacks"  # @@map("feedbacks")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column("user_id", Integer, ForeignKey("users.id"))
    message_id: Mapped[int] = mapped_column("message_id", Integer, ForeignKey("messages.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column("conversation_id", Integer)
    rating: Mapped[int] = mapped_column(Integer)  # 1 / -1
    comment: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tags: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="feedbacks")
    message: Mapped["Message"] = relationship(back_populates="feedbacks")

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_feedback_user_message"),  # @@unique([userId, messageId])
        Index("idx_feedback_message", "message_id"),                                  # @@index([messageId])
        Index("idx_feedback_rating_created", "rating", "created_at"),                 # @@index([rating, createdAt])
        Index("idx_feedback_user_created", "user_id", "created_at"),                  # @@index([userId, createdAt])
    )
```

#### 4.1.10 AgentStep 模型

```python
# src/models/agent_step.py
from sqlalchemy import String, Integer, JSON, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Any
from .base import Base, TimestampMixin

class AgentStep(Base, TimestampMixin):
    __tablename__ = "agent_steps"  # @@map("agent_steps")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        "message_id", Integer, ForeignKey("messages.id", ondelete="CASCADE")
    )
    step: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(20))         # @db.VarChar(20)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    args: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # @db.Text
    duration_ms: Mapped[Optional[int]] = mapped_column("duration_ms", Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    message: Mapped["Message"] = relationship(back_populates="steps")

    __table_args__ = (
        Index("idx_agent_steps_msg_step", "message_id", "step"),  # @@index([messageId, step])
    )
```

### 4.2 Prisma 特有概念处理对照

| Prisma 概念 | SQLAlchemy 处理方式 | 示例 |
|---|---|---|
| `@@map("table_name")` | `__tablename__ = "table_name"` | `__tablename__ = "users"` |
| `@map("column_name")` | `mapped_column("column_name", ...)` | `mapped_column("role_id", Integer)` |
| `@default(now())` | `server_default=func.now()` | `created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())` |
| `@updatedAt` | `server_default=func.now(), onupdate=func.now()` | `updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())` |
| `Json` / `Json?` | `JSON` 类型 | `preferences: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)` |
| `@db.Text` | `Text` 类型 | `content: Mapped[str] = mapped_column(Text)` |
| `@db.VarChar(n)` | `String(n)` 类型 | `username: Mapped[str] = mapped_column(String(50))` |
| `enum RoleName` | Python `enum.Enum` + SQLAlchemy `Enum` | `class RoleName(enum.Enum): ADMIN="ADMIN"; USER="USER"` |
| 自引用关系 `parent` | `relationship(remote_side="Trip.id")` | 见 Trip 模型 |
| `onDelete: Cascade` | `ForeignKey(..., ondelete="CASCADE")` + `cascade="all, delete-orphan"` | 见 Message/Feedback/AgentStep |
| `@@index([field1, field2])` | `__table_args__ = (Index(...),)` | 见各模型 |
| `@@unique([f1, f2])` | `__table_args__ = (UniqueConstraint(...),)` | 见 Feedback 模型 |

### 4.3 数据库迁移策略

| 维度 | 策略 |
|---|---|
| **是否执行 Alembic 迁移** | **否**。本次迁移复用现有 Prisma 创建的 MySQL 表结构，Python 端直连同一数据库。Alembic 仓库初始化但不生成/执行迁移脚本。 |
| **与 Prisma 迁移共存** | 迁移完成后，数据库管理权从 Prisma 迁移到 Alembic。后续 schema 变更用 `alembic revision --autogenerate`。 |
| **模型与表结构对齐验证** | 迁移后编写验证脚本：对比 SQLAlchemy 模型 metadata 与 MySQL information_schema，确保字段/索引/约束完全一致。 |
| **JSON 字段兼容** | MySQL `JSON` 类型在 SQLAlchemy 中映射为 `JSON`，读写行为与 Prisma `Json` 一致（自动序列化/反序列化）。 |

### 4.4 关键兼容性问题解决方案

#### 4.4.1 `_count` 嵌套对象实现

Prisma 的 `include: { _count: { select: { messages: true } } }` 在 SQLAlchemy 中需手动查询：

```python
# src/utils/serialization.py
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

async def attach_count(
    session: AsyncSession,
    items: list,
    model_cls,
    count_model_cls,
    fk_field: str,
    group_field: str,
    count_name: str,
    where_filter=None,
):
    """
    为列表项附加 _count 嵌套对象。
    
    示例：为 Conversation 列表附加 _count.messages
    await attach_count(
        session, conversations, Conversation, Message,
        fk_field="conversation_id", group_field="id",
        count_name="messages",
        where_filter=None
    )
    → 每条 conversation 对象增加 _count = {"messages": N}
    """
    ids = [getattr(item, group_field) for item in items]
    if not ids:
        return items
    
    stmt = (
        select(getattr(count_model_cls, fk_field), func.count().label("cnt"))
        .where(getattr(count_model_cls, fk_field).in_(ids))
        .group_by(getattr(count_model_cls, fk_field))
    )
    if where_filter is not None:
        stmt = stmt.where(where_filter)
    
    result = await session.execute(stmt)
    count_map = {row[0]: row[1] for row in result}
    
    for item in items:
        if not hasattr(item, "_count"):
            item._count = {}
        item._count[count_name] = count_map.get(getattr(item, group_field), 0)
    
    return items
```

**使用示例**（ConversationService.list_conversations）：
```python
# 对应 Prisma: include: { _count: { select: { messages: true } } }
conversations = await session.execute(
    select(Conversation).where(Conversation.user_id == user_id)
    .order_by(Conversation.updated_at.desc())
    .offset((page - 1) * pageSize).limit(pageSize)
)
items = conversations.scalars().all()
items = await attach_count(session, items, Conversation, Message,
    fk_field="conversation_id", group_field="id", count_name="messages")
```

#### 4.4.2 snake_case → camelCase 统一序列化方案

使用 Pydantic v2 的 `alias_generator` + `populate_by_name` + `by_alias=True`：

```python
# src/schemas/common.py
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class CamelModel(BaseModel):
    """所有响应模型的基类：自动 snake_case → camelCase"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,  # 允许从 SQLAlchemy ORM 对象直接构造
    )

# 示例：User 响应模型
class UserResponse(CamelModel):
    id: int
    username: str
    email: str
    nickname: str | None = None
    avatar: str | None = None
    phone: str | None = None
    bio: str | None = None
    role_id: int          # 序列化时输出为 "roleId"
    status: int
    created_at: datetime  # 序列化时输出为 "createdAt"
    preferences: dict | None = None

# 使用：UserResponse.model_validate(orm_user).model_dump(by_alias=True)
# → {"id": 1, "username": "foo", "roleId": 2, "createdAt": "...", ...}
```

**关键点**：
- `from_attributes=True`：允许 `UserResponse.model_validate(user_orm_object)` 直接从 SQLAlchemy 对象构造
- `by_alias=True`：序列化时使用 camelCase 别名
- `_count` 字段：在 schema 中声明为 `count_: dict | None = Field(None, alias="_count")`

#### 4.4.3 JSON 字段读写

```python
# 写入：直接传 Python dict/list，SQLAlchemy JSON 类型自动序列化
user = User(username="foo", preferences={"interests": ["food", "history"]})
session.add(user)
await session.commit()

# 读取：自动反序列化为 Python dict/list
user = await session.get(User, 1)
print(user.preferences)  # {"interests": ["food", "history"]}

# Spot.tags（JSON 数组）
spot = Spot(name="故宫", tags=["历史", "文化", "皇宫"], ...)
# 读取：spot.tags → ["历史", "文化", "皇宫"]
```

---

## 5. API 接口设计

### 5.1 路由组织

```python
# src/app.py
from fastapi import FastAPI
from .routers import (
    user, trip, conversation, history,
    knowledge, stats, feedback, trace, mcp
)

def create_app() -> FastAPI:
    app = FastAPI(title="Trip Server Py", docs_url="/api/docs")
    
    # 中间件链
    app.add_middleware(CORSMiddleware, ...)  # CORS
    app.state.limiter = limiter             # slowapi
    
    # 路由挂载（与 Node.js 完全一致的路径）
    app.include_router(user.router,          prefix="/api/user")
    app.include_router(trip.router,          prefix="/api/trip")
    app.include_router(conversation.router,  prefix="/api/conversations")
    app.include_router(history.router,       prefix="/api/history")
    app.include_router(knowledge.router,     prefix="/api/knowledge")
    app.include_router(stats.router,         prefix="/api/stats")
    app.include_router(feedback.router,      prefix="/api/feedback")
    app.include_router(trace.router,         prefix="/api/admin/agent-trace")
    app.include_router(mcp.router,           prefix="/api/admin")
    
    return app
```

### 5.2 完整端点清单

| 路径 | 方法 | 请求模型 | 响应模型 | 格式 | 鉴权 | 说明 |
|---|---|---|---|---|---|---|
| `/api/user/register` | POST | `RegisterRequest` | `UserLoginResponse` | B | 否（限流） | 用户注册 |
| `/api/user/login` | POST | `LoginRequest` | `UserLoginResponse` | B | 否（限流） | 用户登录 |
| `/api/user/info` | GET | - | `UserResponse` | B | 是 | 获取用户信息 |
| `/api/user/info` | PUT | `UpdateUserRequest` | `UserResponse` | B | 是 | 更新用户信息 |
| `/api/user/password` | PUT | `ChangePasswordRequest` | `SuccessResponse` | B | 是 | 修改密码 |
| `/api/user/forgot-password` | POST | `ForgotPasswordRequest` | `SuccessResponse` | B | 否（限流） | 忘记密码 |
| `/api/user/reset-password` | POST | `ResetPasswordRequest` | `SuccessResponse` | B | 否（限流） | 重置密码 |
| `/api/trip/recommend` | POST | `RecommendRequest` | `RecommendResponse` | **A** | 是（限流+幂等+预算+并发） | 行程推荐（同步） |
| `/api/trip/chat` | POST | `ChatRequest` | SSE Stream | - | 是（限流+预算+并发） | SSE 流式对话 |
| `/api/conversations` | GET | `?page&pageSize` | `PaginatedResponse[ConversationListItem]` | B | 是 | 对话列表（含 _count） |
| `/api/conversations/{id}` | GET | - | `ConversationDetail` | B | 是 | 对话详情（含 messages） |
| `/api/conversations/{id}` | DELETE | - | `SuccessResponse` | B | 是 | 删除对话 |
| `/api/history/trips` | GET | `?page&pageSize` | `PaginatedResponse[TripListItem]` | B | 是 | 行程历史列表 |
| `/api/history/trips/{id}` | GET | - | `TripDetail` | B | 是 | 行程详情 |
| `/api/history/trips/{id}` | DELETE | - | `SuccessResponse` | B | 是 | 删除行程 |
| `/api/knowledge/spots` | GET | `?city&category&page&pageSize` | `PaginatedResponse[SpotResponse]` | B | 是 | 景点列表 |
| `/api/knowledge/spots/{id}` | GET | - | `SpotResponse` | B | 是 | 景点详情 |
| `/api/knowledge/spots` | POST | `SpotInput` | `SpotResponse` | B | 是（admin） | 创建景点 |
| `/api/knowledge/spots/{id}` | PUT | `SpotUpdateInput` | `SpotResponse` | B | 是（admin） | 更新景点 |
| `/api/knowledge/spots/{id}` | DELETE | - | `SuccessResponse` | B | 是（admin） | 删除景点 |
| `/api/stats/token-usage/stats` | GET | `?requestType&userId` | `TokenAggregate` | B | 是 | Token 用量统计 |
| `/api/stats/token-usage/logs` | GET | `?limit` | `list[TokenMetrics]` | B | 是 | Token 用量日志 |
| `/api/feedback` | POST | `FeedbackInput` | `SuccessResponse` | B | 是（限流） | 提交反馈 |
| `/api/feedback/message/{id}` | GET | - | `FeedbackStats` | B | 是 | 消息反馈统计 |
| `/api/feedback/stats` | GET | - | `GlobalFeedbackStats` | B | 是 | 全局统计 |
| `/api/feedback/list/{msgId}` | GET | - | `list[FeedbackResponse]` | B | 是 | 消息反馈列表 |
| `/api/feedback/admin/high-token-low-satisfaction` | GET | - | `list[dict]` | B | 是 | 高 token 低满意案例 |
| `/api/feedback/admin/daily-stats` | GET | - | `list[DailyStats]` | B | 是 | 日维度统计 |
| `/api/feedback/admin/convert-to-fixture` | POST | - | `dict` | B | 是 | 转 fixture（P2） |
| `/api/admin/agent-trace/{messageId}` | GET | - | `list[AgentStepResponse]` | B | 是 | 单消息 trace |
| `/api/admin/agent-trace` | GET | `?conversationId&limit` | `list[TraceSummary]` | B | 是 | 会话 trace 摘要 |
| `/api/admin/mcp-stats` | GET | - | `McpStatsResponse` | B | 是（admin） | MCP 状态 |

### 5.3 双响应格式统一处理方案

#### 5.3.1 格式 A 响应封装器（success/data）

```python
# src/schemas/common.py
from typing import Any, Optional
from pydantic import BaseModel

class FormatAResponse(BaseModel):
    """格式 A：用于 /api/trip/recommend"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None

# 使用：
# return FormatAResponse(success=True, data={...})
# return FormatAResponse(success=False, error="推荐失败")
```

#### 5.3.2 格式 B 响应封装器（code/data/message）

```python
class FormatBResponse(BaseModel):
    """格式 B：用于所有其他接口"""
    code: int = 200
    data: Optional[Any] = None
    message: Optional[str] = None
    error: Optional[str] = None

class SuccessResponse(FormatBResponse):
    code: int = 200
    message: str = "操作成功"

class PaginatedResponse(BaseModel):
    """分页响应（格式 B 的 data 字段）"""
    items: list
    total: int
    page: int
    pageSize: int
```

#### 5.3.3 统一异常处理中间件

```python
# src/exceptions.py
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# 自定义异常
class BusinessError(Exception):
    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code

class AuthError(Exception):
    def __init__(self, message: str = "未登录"):
        self.message = message
        self.code = 401

# 异常处理器注册
def register_exception_handlers(app: FastAPI):
    
    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, exc: BusinessError):
        return JSONResponse(
            status_code=exc.code,
            content={"code": exc.code, "error": exc.message},
        )
    
    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError):
        return JSONResponse(
            status_code=401,
            content={"code": 401, "error": exc.message},
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={"code": 400, "error": "参数错误"},
        )
    
    @app.exception_handler(Exception)
    async def global_error_handler(request: Request, exc: Exception):
        logger.error("未捕获异常", error=str(exc), path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"code": 500, "error": "服务器内部错误"},
        )
```

### 5.4 核心 Pydantic 请求/响应模型设计

```python
# src/schemas/user.py
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class UserLoginResponse(CamelModel):
    id: int
    username: str
    email: str
    nickname: str | None = None
    avatar: str | None = None
    phone: str | None = None
    bio: str | None = None
    role_id: int
    token: str

class UpdateUserRequest(BaseModel):
    nickname: str | None = None
    avatar: str | None = None
    phone: str | None = None
    bio: str | None = None
    preferences: dict | None = None

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str

# src/schemas/trip.py
class RecommendRequest(BaseModel):
    city: str
    budget: int
    days: int
    departure_city: str | None = None

class ChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None

class TripDataResponse(CamelModel):
    """recommend/optimize 的 data 字段"""
    id: int | None = None
    city: str
    days: int
    total_budget: int | None = None
    daily_itinerary: list | None = None
    budget_breakdown: dict | None = None
    tips: list | None = None
    warnings: list | None = None

# src/schemas/conversation.py
class ConversationListItem(CamelModel):
    id: int
    user_id: int
    title: str | None = None
    summary: str | None = None
    created_at: datetime
    updated_at: datetime
    count: dict = Field(default_factory=dict, alias="_count")
    # → _count: {"messages": N}

class MessageResponse(CamelModel):
    id: int
    conversation_id: int
    role: str
    content: str
    metadata_: dict | None = Field(None, alias="metadata")
    excluded_from_context: bool | None = None
    created_at: datetime

class ConversationDetail(CamelModel):
    id: int
    user_id: int
    title: str | None = None
    summary: str | None = None
    recap: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []

# src/schemas/spot.py
class SpotInput(BaseModel):
    name: str
    city: str
    category: str
    description: str
    tags: list
    avg_cost: float | None = None
    duration: str | None = None
    open_time: str | None = None
    rating: float | None = None

class SpotResponse(CamelModel):
    id: int
    name: str
    city: str
    category: str
    description: str
    tags: list
    avg_cost: float | None = None
    duration: str | None = None
    open_time: str | None = None
    rating: float | None = None
    vector_id: str | None = None
    created_at: datetime
    updated_at: datetime

# src/schemas/sse.py
class SSEPayload(BaseModel):
    """SSE 事件 data 字段"""
    type: str  # chunk/complete/error/tool_start/tool_end/heartbeat
    name: str | None = None
    content: str | None = None
    data: Any | None = None
```

---

## 6. SSE 流式对话实现方案（CRITICAL — 最高风险模块）

### 6.1 架构概览

```mermaid
graph LR
    subgraph "正常流式路径"
        A1[POST /api/trip/chat] --> A2[Auth + RateLimit]
        A2 --> A3[create_resumable_stream]
        A3 --> A4[Redis: createStream]
        A4 --> A5[Set X-Stream-Id header]
        A5 --> A6[StreamingResponse async generator]
        A6 --> A7[AgentEngine.chat callbacks]
        A7 --> A8[send chunk/tool_start/tool_end]
        A8 --> A9[write SSE + Redis appendEvent]
        A9 --> A10[send complete + end]
        A10 --> A11[Redis markComplete]
    end

    subgraph "断点续传路径"
        B1[POST /api/trip/chat<br/>+ X-Stream-Id + Last-Event-ID] --> B2[resume_stream]
        B2 --> B3[Redis: getStreamState]
        B3 --> B4{IDOR check<br/>userId match?}
        B4 -->|Yes| B5[Redis: getEventsSince]
        B5 --> B6[Replay events via SSE]
        B6 --> B7[Send end event]
    end

    subgraph "Redis 存储"
        R1[HASH: stream:uuid<br/>status/userId/conversationId]
        R2[LIST: stream:uuid:events<br/>JSON events]
        R3[STRING: stream:uuid:seq<br/>INCR counter]
        R1 -.-> R2 -.-> R3
    end

    A4 --> R1
    A9 --> R2 & R3
    B3 --> R1 & R3
    B5 --> R2
```

### 6.2 FastAPI SSE 实现方案

```python
# src/controllers/trip_controller.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter()

@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    stream_id_header = request.headers.get("X-Stream-Id")
    last_event_id_header = request.headers.get("Last-Event-ID")

    # ─── 续传路径 ───
    if stream_id_header and last_event_id_header:
        last_seq = int(last_event_id_header)
        return await _handle_resume(
            request, stream_id_header, last_seq, current_user
        )

    # ─── 正常流式路径 ───
    if not body.message:
        return JSONResponse(status_code=400, content={"code": 400, "error": "参数错误"})

    return await _handle_new_stream(body, current_user)


async def _handle_new_stream(body: ChatRequest, user: User) -> StreamingResponse:
    """创建新的可续传 SSE 流"""
    stream_manager = StreamManager()
    
    # 创建 Redis stream，获取 stream_id
    stream_id = await stream_manager.create_stream(
        user_id=str(user.id),
        conversation_id=str(body.conversation_id or "pending"),
    )

    async def event_generator():
        """async generator：产出 SSE 事件"""
        local_seq = 0
        client_connected = True
        abort_event = asyncio.Event()

        async def send(payload: SSEPayload) -> None:
            """发送 SSE 事件：先写 SSE 流，再写 Redis（双写）"""
            nonlocal local_seq
            local_seq += 1
            sse_line = f"id: {local_seq}\ndata: {json.dumps(payload.model_dump(), ensure_ascii=False)}\n\n"
            yield sse_line  # 通过 generator yield 发送
            # Redis 双写（fire-and-forget）
            if stream_id:
                asyncio.create_task(
                    stream_manager.append_event(stream_id, payload)
                )

        # 5s 心跳任务
        async def heartbeat():
            while client_connected and not abort_event.is_set():
                await asyncio.sleep(5)
                if client_connected:
                    yield "id: 0\ndata: " + json.dumps({"type": "heartbeat"}) + "\n\n"

        # 启动 Agent
        try:
            last_usage = None

            def on_chunk(chunk: str):
                nonlocal local_seq
                local_seq += 1
                # 这里需要用同步方式 yield，改为通过 queue
                pass

            # 使用 asyncio.Queue 解耦 agent 回调与 SSE 生成器
            queue: asyncio.Queue = asyncio.Queue()
            
            async def on_event(event: dict):
                await queue.put(event)

            # 启动 agent 任务
            agent_task = asyncio.create_task(
                trip_service.chat_stream(
                    user_id=user.id,
                    message=body.message,
                    conversation_id=body.conversation_id,
                    callbacks=ChatStreamCallbacks(
                        on_chunk=lambda c: queue.put_nowait({"type": "chunk", "content": c}),
                        on_tool_start=lambda n: queue.put_nowait({"type": "tool_start", "name": n}),
                        on_tool_end=lambda n: queue.put_nowait({"type": "tool_end", "name": n}),
                        on_usage=lambda u: setattr(heartbeat, '_last_usage', u),
                    ),
                    signal=abort_event,
                )
            )

            # 心跳任务
            heartbeat_task = asyncio.create_task(_heartbeat_loop(queue, abort_event))

            # 从 queue 消费事件并产出 SSE
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=6.0)
                except asyncio.TimeoutError:
                    # 超时无事件，发心跳
                    event = {"type": "heartbeat"}

                local_seq += 1
                sse_data = json.dumps(event, ensure_ascii=False)
                yield f"id: {local_seq}\ndata: {sse_data}\n\n"

                # Redis 双写
                if stream_id:
                    asyncio.create_task(stream_manager.append_event(stream_id, event))

                if event.get("type") == "complete":
                    break
                if event.get("type") == "error":
                    break

            # 等待 agent 完成
            result = await agent_task
            heartbeat_task.cancel()

            # 标记完成
            if stream_id:
                asyncio.create_task(stream_manager.mark_complete(stream_id))

        except asyncio.CancelledError:
            # 客户端断开
            abort_event.set()
            raise
        except Exception as e:
            local_seq += 1
            error_event = {"type": "error", "error": str(e)}
            yield f"id: {local_seq}\ndata: {json.dumps(error_event)}\n\n"

    # 设置 SSE 响应头
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if stream_id:
        headers["X-Stream-Id"] = stream_id

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
```

### 6.3 X-Stream-Id 生成与管理

```python
# src/services/sse/stream_store.py
import uuid

async def create_stream(user_id: str, conversation_id: str) -> str:
    """创建新 stream，返回 stream_id（格式 stream:{uuid}）"""
    stream_id = f"stream:{uuid.uuid4()}"
    now = int(time.time() * 1000)

    pipe = redis.pipeline()
    pipe.hset(stream_id, mapping={
        "userId": user_id,
        "conversationId": conversation_id,
        "status": "active",
        "createdAt": str(now),
        "lastEventAt": str(now),
    })
    pipe.set(f"{stream_id}:seq", 0)
    pipe.expire(stream_id, TTL_SECONDS)         # 600s
    pipe.expire(f"{stream_id}:seq", TTL_SECONDS)
    await pipe.execute()

    return stream_id
```

### 6.4 Redis 双写实现

```python
# src/services/sse/stream_store.py
import json
import time
import uuid
from ...config.redis_client import redis, is_redis_available

TTL_SECONDS = 600  # 10 分钟
MAX_EVENT_SIZE = 64 * 1024  # 64KB

async def append_event(stream_id: str, event: dict) -> int:
    """
    追加 event 到 stream，原子自增 seq。
    返回 seq。
    """
    serialized = json.dumps(event, ensure_ascii=False)
    if len(serialized.encode()) > MAX_EVENT_SIZE:
        raise ValueError(f"Event too large: {len(serialized)} bytes (max {MAX_EVENT_SIZE})")

    # 原子自增 seq
    seq = await redis.incr(f"{stream_id}:seq")
    now = int(time.time() * 1000)

    full_event = {"seq": seq, "type": event["type"], "data": event, "createdAt": now}

    pipe = redis.pipeline()
    pipe.rpush(f"{stream_id}:events", json.dumps(full_event))
    pipe.hset(stream_id, "lastEventAt", str(now))
    pipe.expire(stream_id, TTL_SECONDS)
    pipe.expire(f"{stream_id}:events", TTL_SECONDS)
    pipe.expire(f"{stream_id}:seq", TTL_SECONDS)
    await pipe.execute()

    return seq

async def get_events_since(stream_id: str, last_seq: int) -> list[dict]:
    """获取 seq > last_seq 的所有 events"""
    state = await get_stream_state(stream_id)

    if last_seq > state["totalSeq"]:
        raise ValueError(f"Last-Event-ID {last_seq} exceeds totalSeq {state['totalSeq']}")

    if last_seq >= state["totalSeq"]:
        return []

    # LRANGE：seq 从 1 开始 → events[0] = seq 1
    start_idx = last_seq
    raw = await redis.lrange(f"{stream_id}:events", start_idx, -1)

    events = []
    for s in raw:
        try:
            events.append(json.loads(s))
        except json.JSONDecodeError:
            logger.warning("损坏 event 跳过", stream_id=stream_id, raw=s[:100])

    return events

async def get_stream_state(stream_id: str) -> dict:
    """获取 stream 状态（用于续传 + IDOR 防护）"""
    hash_data = await redis.hgetall(stream_id)
    if not hash_data or "userId" not in hash_data:
        raise ValueError(f"Stream not found: {stream_id}")

    seq_str = await redis.get(f"{stream_id}:seq")
    total_seq = int(seq_str) if seq_str else 0

    return {
        "streamId": stream_id,
        "userId": hash_data["userId"],
        "conversationId": hash_data["conversationId"],
        "status": hash_data["status"],
        "createdAt": int(hash_data["createdAt"]),
        "lastEventAt": int(hash_data["lastEventAt"]),
        "totalSeq": total_seq,
    }

async def mark_complete(stream_id: str) -> None:
    await redis.hset(stream_id, "status", "completed")
```

### 6.5 Last-Event-ID 断点续传实现

```python
# src/services/sse/stream_manager.py
from fastapi.responses import StreamingResponse
import json

async def resume_stream(stream_id: str, last_seq: int, user_id: str) -> StreamingResponse:
    """
    断点续传：重发 last_seq 之后的所有 events。
    
    错误类型：
    - StreamNotFoundError → 404
    - StreamForbiddenError → 403（IDOR 防护）
    - StreamBadRequestError → 400（lastSeq 超界）
    """
    # 获取 stream 状态
    try:
        state = await get_stream_state(stream_id)
    except ValueError:
        raise StreamNotFoundError(stream_id)

    # IDOR 防护
    if str(state["userId"]) != str(user_id):
        raise StreamForbiddenError()

    # 获取缺失 events
    try:
        events = await get_events_since(stream_id, last_seq)
    except ValueError as e:
        raise StreamBadRequestError(str(e))

    async def replay_generator():
        for ev in events:
            payload = ev["data"]
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield 'event: end\ndata: {"done":true}\n\n'

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "X-Stream-Id": stream_id,
    }

    return StreamingResponse(
        replay_generator(),
        media_type="text/event-stream",
        headers=headers,
    )
```

### 6.6 六种事件类型发送逻辑

| 事件类型 | 触发时机 | data 字段 | Redis 双写 |
|---|---|---|---|
| `chunk` | LLM 流式输出每个 token 片段 | `{"type": "chunk", "content": "片段文本"}` | 是 |
| `tool_start` | 工具调用开始 | `{"type": "tool_start", "name": "retrieve_knowledge"}` | 是 |
| `tool_end` | 工具调用结束 | `{"type": "tool_end", "name": "retrieve_knowledge"}` | 是 |
| `complete` | Agent 执行完成 | `{"type": "complete", "data": {"conversationId": 123, "usage": {"prompt": 100, "completion": 200, "total": 300}}}` | 是 |
| `error` | Agent 执行异常 | `{"type": "error", "error": "错误信息"}` | 是 |
| `heartbeat` | 每 5 秒 | `{"type": "heartbeat"}` | 是 |

### 6.7 5s 心跳实现

```python
async def _heartbeat_loop(queue: asyncio.Queue, abort_event: asyncio.Event):
    """独立心跳协程：每 5 秒向 queue 推入 heartbeat 事件"""
    while not abort_event.is_set():
        await asyncio.sleep(5)
        if not abort_event.is_set():
            queue.put_nowait({"type": "heartbeat"})
```

### 6.8 客户端断开检测

```python
# FastAPI 的 StreamingResponse 在客户端断开时会触发 asyncio.CancelledError
# 在 event_generator 中捕获即可

async def event_generator():
    try:
        # ... 正常流式逻辑 ...
        yield sse_data
    except asyncio.CancelledError:
        # 客户端断开（AbortController 或网络断开）
        logger.warning("客户端断开，已中止 Agent")
        abort_event.set()
        # 强制持久化当前已生成的回复
        raise  # 重新抛出，让 FastAPI 正确清理
```

**关键差异**：Node.js 使用 `req.on('close')` 检测客户端断开；FastAPI 使用 `asyncio.CancelledError` 捕获。FastAPI 的 `StreamingResponse` 在客户端断开时会取消生成器协程，触发 `CancelledError`。

### 6.9 与现有 Node.js SSE 实现的差异点和注意事项

| 维度 | Node.js (Express) | Python (FastAPI) | 注意事项 |
|---|---|---|---|
| **响应写入** | `res.write(data)` 同步 | `yield data` 异步生成器 | Python 使用 async generator，不能在回调中直接 yield |
| **客户端断开** | `req.on('close')` 事件 | `asyncio.CancelledError` 异常 | Python 在 generator 中捕获 CancelledError |
| **响应头 flush** | `res.flushHeaders()` | StreamingResponse 自动发送 headers | FastAPI 在返回 StreamingResponse 时自动发送 headers |
| **并发模型** | 单线程 Event Loop | 单线程 asyncio Event Loop | 两者一致，但 Python 需注意阻塞调用 |
| **Redis 管道** | `redis.pipeline()` | `redis.pipeline()` | redis-py 的 pipeline 与 ioredis 接口接近 |
| **AbortController** | `new AbortController()` 传 signal | `asyncio.Event()` 传 abort_event | Python 用 Event 替代 AbortSignal |
| **心跳定时器** | `setInterval(fn, 5000)` | `asyncio.create_task(heartbeat_loop())` | Python 用 async task 替代 setInterval |
| **队列解耦** | 直接在回调中 `res.write()` | `asyncio.Queue` 解耦回调与 generator | **关键**：Python 的 async generator 不能在回调中 yield，必须通过 Queue 中转 |

---

## 7. AI 编排层设计

### 7.1 LangGraph Python 迁移方案

#### 7.1.1 状态定义差异

```python
# src/services/agent/state.py
# LangGraph Python 使用 TypedDict 替代 Annotation.Root
from typing import TypedDict, Optional, Any
from langchain_core.messages import BaseMessage

class PlannerState(TypedDict):
    # 输入
    user_id: int
    message: str
    city: str
    budget: Optional[int]
    days: Optional[int]
    departure_city: Optional[str]
    user_preferences: Optional[dict]
    conversation_history: list[BaseMessage]
    # research 产出
    research_bundle: dict  # ResearchBundle
    # planner 产出
    raw_output: Optional[str]
    parsed: Optional[dict]  # TripContent
    # 元数据
    usage: dict  # TokenUsage
    route: Optional[str]  # 'planning' | 'general'
    errors: list[str]
```

**与 JS 版差异**：
- JS: `Annotation.Root({...})` → Python: `TypedDict`
- JS: `Annotation<number>` → Python: 直接类型注解 `int`
- LangGraph Python 自动处理 TypedDict 的字段合并（默认覆盖语义，与 JS Annotation 默认行为一致）

#### 7.1.2 ChatGraph 状态图定义

```python
# src/services/agent/chat_graph.py
from langgraph.graph import StateGraph, END
from .state import PlannerState
from .nodes.router import router_node
from .nodes.research import research_node
from .nodes.chat_planner import chat_planner_node
from .nodes.legacy_agent import legacy_agent_node

def build_chat_graph():
    graph = StateGraph(PlannerState)

    graph.add_node("router", router_node)
    graph.add_node("research", research_node)
    graph.add_node("chat_planner", chat_planner_node)
    graph.add_node("legacy_agent", legacy_agent_node)

    graph.set_entry_point("router")  # 对应 JS: addEdge('__start__', 'router')

    graph.add_conditional_edges(
        "router",
        lambda state: "research" if state["route"] == "planning" else "legacy_agent",
    )
    graph.add_edge("research", "chat_planner")
    graph.add_edge("chat_planner", END)
    graph.add_edge("legacy_agent", END)

    return graph.compile()
```

#### 7.1.3 PlannerGraph 状态图定义

```python
# src/services/agent/planner_graph.py
from langgraph.graph import StateGraph, END
from .state import PlannerState
from .nodes.research import research_node
from .nodes.planner import planner_node, retry_planner_node
from .nodes.validate import validate_node

def build_planner_graph():
    graph = StateGraph(PlannerState)

    graph.add_node("research", research_node)
    graph.add_node("planner", planner_node)
    graph.add_node("validate", validate_node)
    graph.add_node("retry_planner", retry_planner_node)

    graph.set_entry_point("research")  # 对应 JS: addEdge('__start__', 'research')
    graph.add_edge("research", "planner")
    graph.add_edge("planner", "validate")
    graph.add_conditional_edges(
        "validate",
        lambda state: END if state.get("parsed") else "retry_planner",
    )
    graph.add_edge("retry_planner", END)

    return graph.compile()
```

#### 7.1.4 节点迁移对照

| 节点 | JS 实现要点 | Python 迁移要点 | API 差异 |
|---|---|---|---|
| **router** | `isPlanningRequest(message)` → 返回 `{route, city}` | 逻辑完全一致，Python 正则用 `re` 模块 | 无差异 |
| **research** | `Promise.allSettled(tasks.map(t => t.fn()))` 并行 | `asyncio.gather(*tasks, return_exceptions=True)` | JS `allSettled` → Python `gather(return_exceptions=True)` |
| **planner** | LLM 调用 + JSON 解析 | langchain-openai `ChatOpenAI` Python 版 | `modelKwargs` → `model_kwargs` |
| **chatPlanner** | LLM 流式调用 + system prompt | 同上，流式用 `astream()` | JS `streamEvents(v2)` → Python `astream()` 或 `astream_events()` |
| **validate** | `validateWithRepair(rawOutput)` JSON 修复 | Python `json.loads` + json修复逻辑 | JSON 修复逻辑需移植 |
| **legacy_agent** | `AgentExecutor.streamEvents(input, {version: 'v2'})` | `agent.astream_events(input, version='v2')` | Python LangGraph 推荐用 `astream_events` |

#### 7.1.5 工具迁移对照

| 工具 | JS 实现 | Python 实现 | 差异 |
|---|---|---|---|
| **retrieve_knowledge** | `DynamicStructuredTool({name, description, schema, func})` | `@tool` 装饰器 + Pydantic args | JS 用 Zod schema → Python 用 Pydantic + `@tool` |
| **calculate_distance** | 同上 | 同上 | 逻辑一致 |
| **search_hotels** | 同上 | 同上 | 逻辑一致 |
| **amap tools** | `DynamicTool` 动态加载 | `StructuredTool.from_function` 或 `@tool` | 动态加载逻辑需适配 |

```python
# src/services/agent/tools/retrieve_knowledge.py
from langchain_core.tools import tool
from pydantic import BaseModel, Field

class RetrieveKnowledgeInput(BaseModel):
    query: str = Field(description="搜索关键词，描述你想了解的景点主题")
    city: str = Field(description="目标城市名")
    category: str | None = Field(None, description="景点类型：景点/美食/住宿/交通")

@tool(args_schema=RetrieveKnowledgeInput)
async def retrieve_knowledge(query: str, city: str, category: str | None = None) -> str:
    """从旅行知识库检索景点、美食、住宿、交通等真实信息。
    当用户询问某个城市具体的景点推荐、美食、交通、住宿时，必须调用此工具获取真实数据。"""
    results = await search_spots(query=query, city=city, category=category, limit=5)
    if not results:
        return f"知识库中没有找到 {city} 的相关信息。"
    return results
```

### 7.2 RAG 检索引擎迁移

#### 7.2.1 三路并行召回

```python
# src/services/knowledge_service.py (search_spots 函数)
import asyncio

async def search_spots(query: str, city: str, category: str | None = None, limit: int = 5) -> str:
    # 本地查询改写
    rewritten_query = await rewrite_query(query, city)

    # 三路并行召回
    chroma_available = await check_chroma_health()

    tasks = []
    # 路径 1: Chroma 向量检索
    if chroma_available:
        tasks.append(_chroma_search(rewritten_query, city, category))
    else:
        tasks.append(asyncio.coroutine(lambda: [])())  # 空结果

    # 路径 2: MySQL 关键词检索
    tasks.append(_mysql_keyword_search(city, extract_keywords(query), category, 10))

    # 路径 3: MySQL rating 排序
    tasks.append(_mysql_rating_search(city, category, 10))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    path1 = results[0] if not isinstance(results[0], Exception) else []
    path2 = results[1] if not isinstance(results[1], Exception) else []
    path3 = results[2] if not isinstance(results[2], Exception) else []

    # RRF 融合
    fused = rrf_fuse(path1, path2, path3)

    # Cross-Encoder 重排
    rerank_candidates = fused[:20]
    skip_rerank = len(rerank_candidates) > 0 and rerank_candidates[0]["rrf_score"] > 0.04

    if len(rerank_candidates) > 1 and not skip_rerank:
        try:
            reranked = await rerank_top_k(
                rewritten_query,
                [c["desc"] for c in rerank_candidates],
                min(len(fused), 20),
            )
            # 按 rerank 得分重新映射
            reranked_map = {r["text"]: i for i, r in enumerate(reranked)}
            reranked_items = sorted(
                rerank_candidates,
                key=lambda x: reranked_map.get(x["desc"], fused.index(x)),
            )[:limit]
            return _format_results(reranked_items)
        except Exception:
            pass  # 降级到 RRF 排序

    final_items = fused[:limit]
    return _format_results(final_items)
```

#### 7.2.2 ChromaDB Python client 接入

```python
# src/config/chroma_client.py
import chromadb
from .settings import settings

_client = None
_collection = None

def get_chroma_client() -> chromadb.AsyncClient:
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _client

async def get_spots_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = await client.get_or_create_collection(
            name="travel_spots",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection

async def check_chroma_health() -> bool:
    try:
        client = get_chroma_client()
        await client.heartbeat()
        return True
    except Exception:
        return False
```

#### 7.2.3 sentence-transformers 接入

```python
# src/config/embeddings.py
from sentence_transformers import SentenceTransformer
from .settings import settings

_model = None

def get_embedder() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(
            "BAAI/bge-small-zh-v1.5",
            device="cpu",
        )
    return _model

def embed_text(text: str) -> list[float]:
    """同步调用（sentence-transformers 尚无原生 async 支持）"""
    model = get_embedder()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()

async def embed_text_async(text: str) -> list[float]:
    """异步包装：在线程池中运行同步 embedding"""
    import asyncio
    return await asyncio.to_thread(embed_text, text)
```

```python
# src/services/rag/reranker.py
from sentence_transformers import CrossEncoder
import torch

_reranker = None

def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder("BAAI/bge-reranker-base")
    return _reranker

async def rerank(query: str, documents: list[str]) -> list[dict]:
    if not documents:
        return []

    try:
        model = get_reranker()
        # Cross-Encoder: query-doc pair scoring
        pairs = [(query, doc) for doc in documents]
        scores = await asyncio.to_thread(model.predict, pairs)

        scored = [
            {"text": doc, "score": float(torch.sigmoid(torch.tensor(score)).item())}
            for doc, score in zip(documents, scores)
        ]
        return sorted(scored, key=lambda x: x["score"], reverse=True)
    except Exception as e:
        logger.warning("重排序失败，使用原始排序", error=str(e))
        return [{"text": doc, "score": 0} for doc in documents]
```

#### 7.2.4 RRF 融合算法

```python
# src/services/rag/rrf.py
RRF_K = 60

def rrf_fuse(path1: list[dict], path2: list[dict], path3: list[dict]) -> list[dict]:
    """RRF 融合：score = Σ 1/(rank + K)"""
    score_map: dict[str, dict] = {}

    def add_path(items: list[dict]):
        for rank, item in enumerate(items):
            key = item["name"]
            if key in score_map:
                score_map[key]["score"] += 1 / (rank + RRF_K)
            else:
                score_map[key] = {"score": 1 / (rank + RRF_K), "item": item}

    add_path(path1)
    add_path(path2)
    add_path(path3)

    result = [
        {**v["item"], "rrf_score": v["score"]}
        for v in score_map.values()
    ]
    return sorted(result, key=lambda x: x["rrf_score"], reverse=True)
```

### 7.3 LLM 守卫迁移

#### 7.3.1 Token 预算（TokenBudgetManager）

```python
# src/services/llm_guard/token_budget.py
import time
import asyncio
from collections import defaultdict

ONE_MINUTE = 60
ONE_HOUR = 3600

class TokenBudgetManager:
    def __init__(
        self,
        user_token_limit: int = 50_000,
        global_token_limit: int = 200_000,
        user_window: int = ONE_HOUR,
        global_window: int = ONE_MINUTE,
    ):
        self.user_limit = user_token_limit
        self.global_limit = global_token_limit
        self.user_window = user_window
        self.global_window = global_window
        self._user_data: dict[int, dict] = {}  # {userId: {total, reset_at}}
        self._global_data = {"total": 0, "reset_at": 0}
        self._lock = asyncio.Lock()

    def check_user_budget(self, user_id: int) -> dict:
        now = time.time()
        entry = self._user_data.get(user_id)
        if not entry or now >= entry["reset_at"]:
            return {"allowed": True, "current": 0, "limit": self.user_limit}
        return {"allowed": entry["total"] < self.user_limit, "current": entry["total"], "limit": self.user_limit}

    # ... check_global_budget, record_user_usage, record_global_usage, get_global_stats, get_user_stats ...

token_budget = TokenBudgetManager()
```

#### 7.3.2 并发守卫

```python
# src/services/llm_guard/semaphore.py
import asyncio

class ConcurrencyGuard:
    def __init__(self, global_max: int = 10, per_user_max: int = 1):
        self._global = asyncio.Semaphore(global_max)
        self._per_user: dict[int, asyncio.Semaphore] = {}
        self._per_user_max = per_user_max
        self._lock = asyncio.Lock()

    async def try_acquire(self, user_id: int) -> tuple[bool, callable]:
        # 全局检查
        if self._global._value <= 0:
            return False, None

        # 单用户检查
        async with self._lock:
            if user_id not in self._per_user:
                self._per_user[user_id] = asyncio.Semaphore(self._per_user_max)
            user_sem = self._per_user[user_id]
            if user_sem._value <= 0:
                return False, None

        # 获取信号量
        await self._global.acquire()
        await user_sem.acquire()

        released = False
        async def release():
            nonlocal released
            if released:
                return
            released = True
            self._global.release()
            user_sem.release()

        return True, release
```

#### 7.3.3 工具缓存

```python
# src/services/llm_guard/tool_cache.py
import numpy as np

class ToolCache:
    """
    按 tool 维度隔离的缓存管理器。
    支持字面归一化 + embedding 归一化（cosine ≥ 0.85）。
    """
    def __init__(self, configs: dict, cache_factory=None):
        self._configs = configs
        self._caches: dict[str, TTLCache] = {}
        for tool_name, cfg in configs.items():
            factory = cache_factory or (lambda c: TTLCache(max_size=c["max_size"], default_ttl=c["ttl_ms"] / 1000))
            self._caches[tool_name] = factory(cfg)

    async def get_or_compute(
        self, tool_name: str, args: dict, compute: callable
    ) -> tuple[str, bool]:
        cfg = self._configs.get(tool_name)
        cache = self._caches.get(tool_name)
        if not cfg or not cache:
            return await compute(), False

        if "embedding_key" not in cfg:
            return await self._literal_lookup(tool_name, args, compute, cache, cfg)
        else:
            return await self._embedding_lookup(tool_name, args, compute, cache, cfg)

    def _make_literal_key(self, tool_name: str, args: dict) -> str:
        normalized = {}
        for k in sorted(args.keys()):
            v = args[k]
            if v is None:
                continue
            normalized[k] = v.strip().lower() if isinstance(v, str) else v
        return f"{tool_name}:{json.dumps(normalized, sort_keys=True)}"

    async def _embedding_lookup(self, tool_name, args, compute, cache, cfg):
        ek = cfg["embedding_key"]
        threshold = ek.get("threshold", 0.85)
        key_text = ek["extractor"](args)
        query_vec = np.array(await embed_text_async(key_text))

        best_sim = -1
        best_entry = None
        for entry in await cache.values():
            if entry["vector"] is None:
                continue
            sim = float(np.dot(query_vec, entry["vector"]))
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry and best_sim >= threshold:
            return best_entry["value"], True

        result = await compute()
        await cache.set(
            f"embed:{key_text}",
            {"value": result, "vector": query_vec.tolist()},
            ttl=cfg["ttl_ms"] / 1000,
        )
        return result, False
```

### 7.4 MCP 集成迁移

#### 7.4.1 stdio JSON-RPC 子进程 client

```python
# src/services/mcp/amap_process.py
import asyncio
import json
from typing import Optional

class AmapMcpProcess:
    def __init__(self):
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stdout_task: Optional[asyncio.Task] = None

    async def start(self):
        self._proc = await asyncio.create_subprocess_exec(
            "npx", "@amap/amap-maps-mcp-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"AMAP_MAPS_API_KEY": settings.amap_api_key, "PATH": ...},
        )
        # 启动 stdout 读取协程
        self._stdout_task = asyncio.create_task(self._read_stdout())

    async def _read_stdout(self):
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            await self._handle_response(line.decode().strip())

    def get_stdin(self):
        return self._proc.stdin if self._proc else None

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def stop(self):
        if self._proc:
            self._proc.terminate()
            await self._proc.wait()
```

```python
# src/services/mcp/amap_client.py
import asyncio
import json

class AmapMcpClient:
    def __init__(self):
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._initialized = False

    async def send_request(self, method: str, params: dict | None = None) -> any:
        proc = amap_process
        if not proc.is_alive():
            raise RuntimeError("MCP process not available")

        self._request_id += 1
        req_id = self._request_id
        request = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        # 超时
        asyncio.create_task(self._timeout(req_id, settings.amap_timeout_ms))

        proc.get_stdin().write((request + "\n").encode())
        await proc.get_stdin().drain()

        return await future

    async def _handle_response(self, line: str):
        msg = json.loads(line)
        if "id" in msg and msg["id"] in self._pending:
            future = self._pending.pop(msg["id"])
            if "error" in msg:
                future.set_exception(RuntimeError(msg["error"]["message"]))
            else:
                future.set_result(msg["result"])

    async def call_tool(self, name: str, args: dict) -> str:
        result = await self.send_request("tools/call", {"name": name, "arguments": args})
        if result.get("isError"):
            raise RuntimeError(f"MCP tool {name} returned error")
        return "\n".join(
            c["text"] for c in result.get("content", [])
            if c.get("type") == "text" and c.get("text")
        )
```

#### 7.4.2 熔断（pybreaker）

```python
# src/services/mcp/amap_guards.py
import pybreaker
import time

amap_breaker = pybreaker.CircuitBreaker(
    fail_max=10,
    reset_timeout=600,  # 10 分钟
    name="amap-mcp",
)

class TokenBucket:
    """令牌桶限流"""
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()

    def try_consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

_cache = {}  # 简单内存缓存

@amap_breaker
async def call_with_guards(tool_name: str, args: dict, cache_ttl: int | None = None) -> str:
    # 缓存检查
    cache_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
    if cache_ttl and cache_ttl != 0 and tool_name in CACHE_ENABLED_TOOLS:
        cached = _cache.get(cache_key)
        if cached and cached["expires_at"] > time.time():
            return cached["value"]

    # 限流
    bucket = _get_bucket(tool_name)
    if not bucket.try_consume():
        raise RuntimeError("AMAP_MCP_RATE_LIMITED")

    # 调用
    result = await amap_client.call_tool(tool_name, args)

    # 缓存写入
    if cache_ttl and tool_name in CACHE_ENABLED_TOOLS:
        _cache[cache_key] = {"value": result, "expires_at": time.time() + (cache_ttl / 1000)}

    return result
```

---

## 8. 鉴权与安全设计

### 8.1 JWT 实现方案

```python
# src/config/jwt_config.py
import jwt
from datetime import datetime, timedelta, timezone
from .settings import settings

def generate_token(user_id: int, username: str, role_id: int) -> str:
    """生成 JWT，payload 格式与 Node.js 完全一致"""
    payload = {
        "userId": user_id,
        "username": username,
        "roleId": role_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),  # JWT_EXPIRES_IN=7d
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

def verify_token(token: str) -> dict | None:
    """验证 JWT，返回 payload 或 None"""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
```

**关键兼容性**：
- Node.js `jsonwebtoken` 默认使用 `HS256` 算法，Python `PyJWT` 也默认 `HS256`
- payload 中的 `exp` 字段：Node.js `expiresIn: '7d'` → Python `timedelta(days=7)`
- payload 字段名 `userId`/`username`/`roleId` 保持 camelCase（与前端一致）

### 8.2 bcrypt 兼容性验证方案

```python
# src/services/user_service.py
import bcrypt

SALT_ROUNDS = 12  # 与 Node.js bcryptjs 一致

def hash_password(password: str) -> str:
    """密码哈希，产生 $2b$ 格式（与 bcryptjs 的 $2a$/$2b$ 兼容）"""
    salt = bcrypt.gensalt(rounds=SALT_ROUNDS)
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, hashed: str) -> bool:
    """验证密码，兼容 $2a$/$2b$ 前缀"""
    return bcrypt.checkpw(password.encode(), hashed.encode())
```

**验证方案**：
1. 用现有 Node.js 注册的用户账号，在 Python 端执行登录
2. Python `bcrypt.checkpw` 能正确验证 Node.js `bcryptjs` 产生的 `$2a$`/`$2b$` 哈希
3. bcrypt 的哈希格式（`$2a$`/`$2b$` + salt + hash）是跨语言标准，两者兼容性已被广泛验证

### 8.3 密码重置流程

```python
# 与 Node.js userService.ts 逻辑完全一致：
# 1. forgot-password: 生成 UUID token → 写入 password_resets 表 → (邮件发送/P1-2 静默)
# 2. reset-password: 验证 token 未过期+未使用 → 更新密码 → 标记 token 已使用
```

### 8.4 CORS 配置

```python
# src/middleware/cors.py
from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app: FastAPI):
    CORS_DEMO_ORIGINS = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:3000",
        "null",  # file:// 双击打开 demo
    ]
    
    env_origins = [o.strip() for o in settings.cors_origin.split(",") if o.strip()]
    demo_origins = CORS_DEMO_ORIGINS if settings.cors_demo else []
    allowed_origins = list(set(env_origins + demo_origins))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-Stream-Id", "Last-Event-ID", "x-request-id"],
        max_age=86400,
    )
```

**注意**：FastAPI 的 CORSMiddleware 不原生支持 `'null'` origin 的特殊处理（Node.js 版自定义了 CORS 逻辑）。需要在中间件中特殊处理 `null` origin：对于 `null` origin，不设置 `Access-Control-Allow-Credentials: true`（与 Node.js 版一致）。

### 8.5 中间件链设计

```
请求 → CORS → 请求ID注入 → 限流(slowapi) → 鉴权(JWT) → 幂等性 → Token预算 → 并发守卫 → 路由处理器
```

```python
# src/middleware/auth.py
from fastapi import Depends, HTTPException, Request
from functools import wraps

async def get_current_user(request: Request) -> dict:
    """JWT 鉴权 Depends"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": 401, "error": "未登录，请先登录"})

    token = auth_header[7:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail={"code": 401, "error": "token无效或已过期"})

    return payload  # {userId, username, roleId}

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """admin 权限检查"""
    if user.get("roleId") != 1:
        raise HTTPException(status_code=403, detail={"code": 403, "error": "权限不足"})
    return user
```

---

## 9. 可观测性设计

### 9.1 日志方案（structlog）

```python
# src/utils/logger.py
import structlog
import logging

def setup_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),  # JSON 输出（对齐 pino）
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO)

# 命名 logger（对齐 Node.js 的命名 logger）
logger = structlog.get_logger()
trip_log = structlog.get_logger("trip")
stream_log = structlog.get_logger("stream")
agent_log = structlog.get_logger("agent")
redis_log = structlog.get_logger("redis")
knowledge_log = structlog.get_logger("knowledge")
```

### 9.2 Agent Trace

```python
# src/services/agent/trace_recorder.py
# 与 Node.js TraceRecorder 逻辑一致：
# - buffer 模式：每个 step add 到内存列表
# - flush 模式：agent 完成后批量 insert
# - 失败只 warn，不影响业务

class TraceRecorder:
    def __init__(self, message_id: int):
        self._message_id = message_id
        self._steps: list[dict] = []

    def add(self, step: dict):
        self._steps.append(step)

    async def flush(self, session: AsyncSession):
        if not self._steps:
            return
        # 批量插入 agent_steps 表
        for step in self._steps:
            db_step = AgentStep(
                message_id=self._message_id,
                step=step["step"],
                type=step["type"],
                name=step.get("name"),
                args=step.get("args"),
                output=step.get("output"),
                duration_ms=step.get("duration_ms"),
                error=step.get("error"),
            )
            session.add(db_step)
        await session.commit()
```

### 9.3 Token 监控

```python
# src/services/agent/observability/token_monitor.py
from collections import deque

MAX_BUFFER_SIZE = 1000
ALERT_HIGH_TOKEN_THRESHOLD = 50_000
ALERT_LOW_CACHE_RATE = 0.3

class TokenMonitor:
    def __init__(self):
        self._buffer: deque = deque(maxlen=MAX_BUFFER_SIZE)

    def record(self, metrics: dict):
        self._buffer.append(metrics)
        # 阈值告警
        if metrics["total_usage"]["total"] > ALERT_HIGH_TOKEN_THRESHOLD:
            logger.warning("Token 消耗超阈值", total_tokens=metrics["total_usage"]["total"])
        # ... 缓存命中率告警 ...

    def aggregate(self, request_type: str | None = None, user_id: int | None = None) -> dict:
        # 与 Node.js 版聚合逻辑一致
        ...

token_monitor = TokenMonitor()
```

### 9.4 指标方案

| 指标 | 来源 | 暴露方式 |
|---|---|---|
| HTTP 请求 QPS / 延迟 | structlog 日志 | 日志分析 |
| Token 用量 | TokenMonitor | `/api/stats/token-usage` |
| Agent Trace | agent_steps 表 | `/api/admin/agent-trace` |
| MCP 调用统计 | amap_guards metrics | `/api/admin/mcp-stats` |
| 缓存命中率 | ToolCache | 日志 |
| Redis 连接状态 | is_redis_available() | 日志 |

---

## 10. 部署架构

### 10.1 开发环境

```bash
# 开发环境：uvicorn 热重载
uv run uvicorn src.main:app --host 0.0.0.0 --port 3000 --reload
```

### 10.2 生产环境

```bash
# 生产环境：gunicorn 多 worker
gunicorn src.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w 4 \
    --bind 0.0.0.0:3000 \
    --timeout 120 \
    --graceful-timeout 30
```

**worker 数量**：`-w 4`（与 Node.js `min(CPU, 8)` 对齐，Python 推荐 `2*CPU+1`，但考虑 LLM I/O 密集型，4 足够）

### 10.3 Docker 化方案

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（sentence-transformers 需要）
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv

# 安装依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 复制源码
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/

EXPOSE 3000

CMD ["uv", "run", "gunicorn", "src.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", "--bind", "0.0.0.0:3000", \
     "--timeout", "120"]
```

```yaml
# docker-compose.yml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "3000:3000"
    env_file: .env
    depends_on:
      - mysql
      - redis
      - chroma
    volumes:
      - ./chroma_data:/app/chroma_data

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-root}
      MYSQL_DATABASE: trip_db
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  chroma:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    volumes:
      - chroma_data:/chroma/chroma

volumes:
  mysql_data:
  redis_data:
  chroma_data:
```

### 10.4 端口规划

| 服务 | 端口 | 说明 |
|---|---|---|
| Python 后端（开发期） | 8000 | 开发期建议用 8000，避免与 Node.js（3000）冲突，两套后端可并行运行 |
| Python 后端（上线后） | 3000 | 与现有 Node.js 一致，前端代理无需改 |
| MySQL | 3306 | 标准（两套后端共享同一 MySQL 实例） |
| Redis | 6379 | 标准（两套后端共享同一 Redis 实例） |
| ChromaDB | 8000 | 标准（两套后端共享同一 ChromaDB 实例） |

### 10.5 与现有 Node.js 后端的并存与切换策略

基于 Q2"一刀切"决策和 PRD 第 11.1 节"同 repo 新目录"代码组织方式，制定以下并存与切换策略：

#### 10.5.1 开发期间：两套后端并行运行

```
trip/                              ← 仓库根目录（主分支）
├── trip-server/     (Node.js :3000)   ← 现有后端，开发期间照常运行，前端默认连这个
├── trip-backend/  (Python  :8000)   ← 新后端，开发期间在 8000 端口运行
└── trip-front/      (Vite    :5173)   ← 前端，VITE_API_TARGET 默认指向 :3000
```

- 现有 `trip-server/` **一行不改**，开发期间前端默认连 Node.js（:3000），保证开发基线可用
- Python 后端在 `:8000` 独立运行，开发测试时把前端 `VITE_API_TARGET` 临时指向 `http://localhost:8000`
- 两套后端**共享同一 MySQL / Redis / ChromaDB 实例**（Q1 决策：保留 MySQL，数据零迁移），便于对比测试响应一致性
- ⚠️ 注意：SSE 流式对话开发期间，Redis 中会同时存在 Node.js 和 Python 写入的 stream 状态，key 前缀需区分（Python 端建议用 `py:stream:` 前缀，避免与 Node.js 的 `stream:` 冲突）

#### 10.5.2 上线切换：一刀切

迁移完成并通过 T14 全量验证后，执行一次性切换：

1. Python 后端监听端口改为 3000（与 Node.js 一致），或保持 8000 但修改前端配置
2. 修改前端 `VITE_API_TARGET` 指向 Python 后端
3. 部署 Python 后端（gunicorn + uvicorn worker）
4. Node.js 后端停止服务（可保留代码作为参考，不立即删除）

#### 10.5.3 回滚方式

若上线后发现问题，回滚零风险：

1. 修改前端 `VITE_API_TARGET` 切回 Node.js 端口（:3000）
2. 重启 Node.js 后端
3. Python 后端问题修复后可再次切换

#### 10.5.4 迁移完成后

验证 Python 后端稳定运行一段时间（建议 1-2 周）后，可考虑：
- 删除 `trip-server/` 目录
- 清理 Node.js 相关依赖（package-lock.json / node_modules）
- 把 `trip-backend/` 重命名为 `trip-server/`（可选）

---

## 11. 技术风险与解决策略（CRITICAL）

### 11.1 🔴 SSE 断点续传（最高风险）

| 维度 | 详情 |
|---|---|
| **风险描述** | FastAPI 的 StreamingResponse + async generator 与 Express 的 res.write 有本质差异。async generator 不能在回调中直接 yield，需要通过 asyncio.Queue 解耦。Redis 双写的原子性、seq 跳号、客户端断开检测都需要重新验证。 |
| **解决策略** | 1. 使用 asyncio.Queue 解耦 agent 回调与 SSE generator（见 6.2 节）<br>2. Redis 双写保持 fire-and-forget 模式（不阻塞 SSE 流）<br>3. seq 使用 Redis INCR 原子自增（与 Node.js 一致）<br>4. 客户端断开通过 asyncio.CancelledError 捕获 |
| **测试策略** | 1. 编写 SSE 断点续传集成测试：模拟客户端中断 → 重连带 X-Stream-Id + Last-Event-ID → 验证续传 events 完整性<br>2. 编写并发 SSE 测试：10 个并发流，验证 seq 不冲突<br>3. 编写 Redis 降级测试：断开 Redis → 验证 SSE 降级为不可续传但不报错<br>4. 编写心跳测试：验证 5s 心跳正确发送 |
| **验收标准** | AC-3：多轮对话、断点续传、心跳、中止、6 种事件类型全部正常工作 |

### 11.2 🟡 Prisma `_count` 兼容

| 维度 | 详情 |
|---|---|
| **风险描述** | Prisma 的 `include: { _count: { select: { messages: true } } }` 是 Prisma 独有语法糖，SQLAlchemy 无原生支持。 |
| **解决策略** | 编写通用 `attach_count()` 工具函数（见 4.4.1 节），在 Service 层批量查询 count 并组装到响应对象。 |
| **测试策略** | 对比测试：同一用户的数据，Node.js 和 Python 返回的 `_count.messages` 值一致。 |

### 11.3 🟡 bcrypt 跨语言兼容性

| 维度 | 详情 |
|---|---|
| **风险描述** | Node.js `bcryptjs` (SALT_ROUNDS=12) 产生的哈希格式为 `$2a$` 或 `$2b$`，Python `bcrypt` 需能验证。 |
| **解决策略** | 1. Python `bcrypt.checkpw` 原生支持 `$2a$`/`$2b$` 前缀<br>2. 迁移前编写验证脚本：从 MySQL 读取现有用户密码哈希，用 Python `bcrypt.checkpw` 验证 |
| **测试策略** | 使用现有 Node.js 注册的账号在 Python 端执行登录，验证密码验证通过。 |
| **验收标准** | AC-8：现有 Node.js 注册的用户可在 Python 端正常登录 |

### 11.4 🟡 LangGraph Python 与 JS 版 API 差异

| 维度 | JS 版 | Python 版 | 适配方案 |
|---|---|---|---|
| **状态定义** | `Annotation.Root({...})` | `TypedDict` | 直接用 TypedDict 替代 |
| **入口边** | `addEdge('__start__', 'node')` | `set_entry_point('node')` | API 名称不同，功能一致 |
| **条件边** | `addConditionalEdges('node', fn)` | `add_conditional_edges('node', fn)` | snake_case 命名 |
| **编译** | `graph.compile()` | `graph.compile()` | 一致 |
| **工具** | `DynamicStructuredTool({schema, func})` | `@tool` 装饰器 + Pydantic | 装饰器风格替代构造器 |
| **流式事件** | `executor.streamEvents(input, {version: 'v2'})` | `agent.astream_events(input, version='v2')` | 方法名不同 |
| **消息类型** | `HumanMessage` / `AIMessage` | `HumanMessage` / `AIMessage` | 一致（langchain_core） |
| **配置注入** | `config.configurable = {...}` | `config = {"configurable": {...}}` | 结构一致 |

### 11.5 🟡 camelCase 序列化

| 维度 | 详情 |
|---|---|
| **风险描述** | 数据库字段为 snake_case（如 `created_at`），前端期望 camelCase（如 `createdAt`）。Prisma 自动转换，Python 需手动处理。 |
| **解决策略** | 使用 Pydantic v2 的 `alias_generator=to_camel` + `by_alias=True` 序列化（见 4.4.2 节）。所有响应模型继承 `CamelModel` 基类。 |
| **测试策略** | 对比测试：同一接口的 Node.js 和 Python 响应 JSON key 完全一致。 |

### 11.6 补充风险

| 风险 | 等级 | 解决策略 |
|---|---|---|
| **sentence-transformers 模型加载阻塞** | 🟡 | 模型在应用启动时预加载（lifespan event），避免首个请求延迟过高 |
| **asyncio 中的同步阻塞调用** | 🟡 | sentence-transformers 的 `encode`/`predict` 是同步调用，必须用 `asyncio.to_thread()` 包装，避免阻塞事件循环 |
| **多 worker 下的 TokenMonitor 状态** | 🟡 | TokenMonitor 使用进程内内存（环形缓冲区），多 worker 下各自独立统计。与 Node.js Cluster 行为一致（每个 worker 独立）。如需全局统计，可迁移到 Redis。 |
| **MCP 子进程管理** | 🟢 | asyncio.subprocess 管理子进程，健康检查 + 自动重启逻辑与 Node.js 一致 |
| **ChromaDB Python client 异步支持** | 🟢 | ChromaDB Python client 有 async API（`AsyncClient`），与 JS 版接口接近 |

---

## 12. 任务分解与开发计划（CRITICAL）

### 12.0 交付节奏说明

> 本项目采用**分阶段交付**（见 PRD 第 11.2 节），对应下方 6 个阶段（T01-T14）。每完成一个阶段，用户 review 一次，不一次性交付全部任务。下方 Gantt 图展示的是理想工期，实际按阶段交付，每阶段间有 review 间隔。

**阶段交付物清单**：

| 阶段 | 完成后用户可 review 到 | 关键验证节点 |
|------|----------------------|-------------|
| 阶段 1（T01-T02） | 可启动的 Python 项目骨架 + 9 张 SQLAlchemy 模型 + 中间件链 | T02 完成后：DB 模型 + 中间件兼容性验证 |
| 阶段 2（T03-T04） | 用户能登录注册 + 对话/行程/景点 CRUD 接口可用 | T03 完成后：用户认证端到端验证（前端能登录） |
| 阶段 3（T05-T08） | RAG 三路召回 + LangGraph 多智能体 + 行程推荐/优化接口可用 | — |
| 阶段 4（T09-T10） | SSE 流式对话 + 断点续传 + 心跳 + 中止全部可用 | T09 完成后：SSE 断点续传集成验证（最高风险） |
| 阶段 5（T11-T13） | 反馈/Token 统计/Agent Trace/MCP 状态接口可用 | — |
| 阶段 6（T14） | 30+ 端点对比测试通过 + 性能基线达标 | T14 完成后：全量 API 对比 + 性能基线验证 |

### 12.1 任务列表

#### 阶段 1：项目骨架与基础设施

| 任务ID | 任务名称 | 描述 | 依赖 | 复杂度 | 模块 |
|---|---|---|---|---|---|
| **T01** | 项目初始化与配置 | pyproject.toml 依赖声明、src/main.py + app.py 入口、config/settings.py 统一配置、Dockerfile + docker-compose.yml、.env.example | 无 | M | 基础设施 |
| **T02** | 数据库模型与中间件 | 9 张 SQLAlchemy 模型、database.py async engine、所有中间件（auth/cors/rate_limiter/idempotency/concurrency_guard/token_budget_guard/request_id）、exceptions.py 全局异常处理、utils/logger.py structlog 配置、utils/serialization.py _count + camelCase 工具 | T01 | L | 数据层 + 中间件 |

#### 阶段 2：核心数据 CRUD

| 任务ID | 任务名称 | 描述 | 依赖 | 复杂度 | 模块 |
|---|---|---|---|---|---|
| **T03** | 用户认证模块 | user router/controller/service、JWT 生成验证、bcrypt 密码哈希、密码重置流程、Pydantic schemas | T02 | M | 认证 |
| **T04** | 对话/行程/景点 CRUD | conversation/history/knowledge router+controller+service、_count 组装、分页、admin 权限控制、Spot CRUD + Chroma 同步 | T02 | M | 数据 CRUD |

#### 阶段 3：AI 基础设施

| 任务ID | 任务名称 | 描述 | 依赖 | 复杂度 | 模块 |
|---|---|---|---|---|---|
| **T05** | RAG 检索引擎 | chroma_client.py、embeddings.py（sentence-transformers）、query_rewriter.py、reranker.py（CrossEncoder）、rrf.py、knowledge_service.search_spots 三路召回+RRF+重排 | T02 | L | RAG |
| **T06** | LangGraph 编排 + LLM 守卫 + MCP | agent_engine.py、chat_graph.py、planner_graph.py、state.py、5 节点、3 工具、system_prompt、trace_recorder、token_monitor、token_budget、semaphore、tool_cache、mcp/amap_process+client+guards+tool_loader | T05 | XL | AI 编排 |
| **T07** | 行程推荐/优化（同步） | trip_service.recommend（PlannerGraph 调用 + geocoding + image fetch + 缓存）、optimize_service、geocode_service、unsplash/image_fetcher | T06 | L | 业务服务 |
| **T08** | 对话摘要压缩 | summary_service.py（分层摘要：关键决策 + 对话脉络 append 模式） | T04 | M | 业务服务 |

#### 阶段 4：SSE 流式对话（最高风险）

| 任务ID | 任务名称 | 描述 | 依赖 | 复杂度 | 模块 |
|---|---|---|---|---|---|
| **T09** | SSE 流式对话（CRITICAL） | sse/stream_store.py（Redis 双写）、sse/stream_manager.py（create_resumable_stream + resume_stream）、trip_controller.chat（StreamingResponse + async generator + asyncio.Queue + 5s 心跳 + 客户端断开检测）、trip_service.chat_stream（增量持久化 + AgentEngine.chat 回调） | T06, T08 | XL | SSE |
| **T10** | SSE 断点续传集成测试 | test_sse/ 断点续传测试、并发测试、Redis 降级测试、心跳测试、中止测试 | T09 | L | 测试 |

#### 阶段 5：增强功能

| 任务ID | 任务名称 | 描述 | 依赖 | 复杂度 | 模块 |
|---|---|---|---|---|---|
| **T11** | 反馈系统 | feedback router/controller/service、feedbacks 提交/统计/admin 分析 | T04 | M | 增强 |
| **T12** | Token 统计 + Agent Trace | stats router/controller、token_usage_log、trace router/controller、trace_service、agent_steps 查询 | T06 | M | 可观测性 |
| **T13** | MCP 状态 API | mcp router/controller、mcp_stats 端点 | T06 | S | 增强 |

#### 阶段 6：集成测试与性能验证

| 任务ID | 任务名称 | 描述 | 依赖 | 复杂度 | 模块 |
|---|---|---|---|---|---|
| **T14** | API 对比测试 + 性能验证 | test_api/ 30+ 端点对比测试（Node.js vs Python 响应一致）、性能基线测试（RAG P50 ≤ 700ms、QPS ≥ 6.0、SSE P99 ≤ 50s）、bcrypt 兼容性验证、前端零改动验证 | T03-T13 | L | 测试 |

### 12.2 任务依赖图

```mermaid
graph TD
    T01[T01: 项目初始化与配置] --> T02[T02: 数据库模型与中间件]
    T02 --> T03[T03: 用户认证模块]
    T02 --> T04[T04: 对话/行程/景点 CRUD]
    T02 --> T05[T05: RAG 检索引擎]
    T05 --> T06[T06: LangGraph编排+LLM守卫+MCP]
    T04 --> T08[T08: 对话摘要压缩]
    T06 --> T07[T07: 行程推荐/优化同步]
    T06 --> T09[T09: SSE流式对话 CRITICAL]
    T08 --> T09
    T09 --> T10[T10: SSE断点续传集成测试]
    T04 --> T11[T11: 反馈系统]
    T06 --> T12[T12: Token统计+AgentTrace]
    T06 --> T13[T13: MCP状态API]
    T03 --> T14[T14: API对比测试+性能验证]
    T04 --> T14
    T05 --> T14
    T07 --> T14
    T09 --> T14
    T10 --> T14
    T11 --> T14
    T12 --> T14
    T13 --> T14
```

### 12.3 开发计划 Gantt 图

> 以下 Gantt 图展示理想工期（约 25 个工作日 / 5 周）。实际采用分阶段交付（见 12.0 节），每阶段间有 review 间隔，总周期会略长于理想工期。

```mermaid
gantt
    title Trip Python 后端迁移开发计划
    dateFormat YYYY-MM-DD
    axisFormat %m/%d

    section 阶段1: 骨架与基础设施
    T01 项目初始化与配置         :t01, 2026-07-11, 2d
    T02 数据库模型与中间件       :t02, after t01, 3d

    section 阶段2: 核心数据CRUD
    T03 用户认证模块             :t03, after t02, 2d
    T04 对话/行程/景点CRUD       :t04, after t02, 3d

    section 阶段3: AI基础设施
    T05 RAG检索引擎             :t05, after t02, 3d
    T06 LangGraph+LLM守卫+MCP   :t06, after t05, 5d
    T07 行程推荐/优化            :t07, after t06, 2d
    T08 对话摘要压缩             :t08, after t04, 2d

    section 阶段4: SSE流式对话
    T09 SSE流式对话 CRITICAL     :t09, after t06, 4d
    T10 SSE断点续传测试          :t10, after t09, 2d

    section 阶段5: 增强功能
    T11 反馈系统                 :t11, after t04, 2d
    T12 Token统计+AgentTrace     :t12, after t06, 2d
    T13 MCP状态API               :t13, after t06, 1d

    section 阶段6: 集成测试
    T14 API对比+性能验证         :t14, after t10, 3d
```

**预估总工期**：约 25 个工作日（5 周）

---

## 13. 依赖包列表

### 13.1 Python 依赖清单

#### 核心依赖

```
# Web 框架
fastapi>=0.111.0
uvicorn>=0.30.0
gunicorn>=22.0.0

# ORM + 数据库
sqlalchemy>=2.0.30
alembic>=1.13.0
aiomysql>=0.2.0          # MySQL async driver

# 数据校验
pydantic>=2.7.0
pydantic-settings>=2.2.0

# Redis
redis>=5.0.0             # async support

# JWT
pyjwt>=2.8.0

# 密码哈希
bcrypt>=4.1.0

# HTTP 客户端
httpx>=0.27.0

# 日志
structlog>=24.1.0
```

#### AI 依赖

```
# LangChain
langchain>=0.2.0
langchain-core>=0.2.0
langchain-openai>=0.1.0
langgraph>=0.1.0

# 向量数据库
chromadb>=0.5.0

# Embedding / Reranker
sentence-transformers>=3.0.0
torch>=2.2.0             # sentence-transformers 依赖
numpy>=1.26.0
```

#### 工具依赖

```
# 限流
slowapi>=0.1.9

# 熔断
pybreaker>=1.1.0

# 定时任务（P2，暂缓）
# apscheduler>=3.10.0
```

#### 开发依赖

```
# 测试
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0            # 测试客户端

# 代码质量
ruff>=0.4.0             # linter + formatter
mypy>=1.10.0            # 类型检查

# 依赖管理
uv>=0.2.0
```

### 13.2 与现有 Node.js 依赖的映射对照表

| Node.js 依赖 | Python 依赖 | 说明 |
|---|---|---|
| `express` ^5.0 | `fastapi` ^0.111 | Web 框架 |
| `@prisma/client` | `sqlalchemy` ^2.0 | ORM |
| `ioredis` | `redis` ^5.0 | Redis 客户端 |
| `jsonwebtoken` | `pyjwt` ^2.8 | JWT |
| `bcryptjs` | `bcrypt` ^4.1 | 密码哈希 |
| `zod` | `pydantic` ^2.7 | 数据校验 |
| `pino` / `pino-http` | `structlog` ^24.1 | 结构化日志 |
| `@langchain/core` | `langchain-core` ^0.2 | LangChain 核心 |
| `@langchain/openai` | `langchain-openai` ^0.1 | LLM 客户端 |
| `@langchain/langgraph` | `langgraph` ^0.1 | 多智能体编排 |
| `@langchain/community` | `langchain` ^0.2 | 社区集成 |
| `chromadb` | `chromadb` ^0.5 | 向量数据库 |
| `@xenova/transformers` | `sentence-transformers` ^3.0 | Embedding/Reranker |
| `opossum` | `pybreaker` ^1.1 | 熔断 |
| `express-rate-limit` | `slowapi` ^0.1 | 限流 |
| `node-cron` | (APScheduler) ^3.10 | 定时任务（P2 暂缓） |
| `node:cluster` | `gunicorn` ^22 | 多进程 |
| `node:child_process` | `asyncio.subprocess` | 子进程管理 |
| `uuid` | `uuid` (stdlib) | UUID 生成 |
| `crypto` | `hashlib` (stdlib) | 加密工具 |

---

## 14. 共享知识（跨文件约定）

### 14.1 命名规范

| 维度 | 规范 | 示例 |
|---|---|---|
| **Python 模块/文件** | snake_case | `user_service.py` |
| **Python 类** | PascalCase | `UserService` |
| **Python 函数/变量** | snake_case | `get_current_user` |
| **数据库表名** | snake_case（与现有一致） | `users`, `conversations` |
| **数据库列名** | snake_case（与现有一致） | `created_at`, `role_id` |
| **API JSON 响应字段** | camelCase（与前端一致） | `createdAt`, `roleId` |
| **API 路径** | kebab-case（与现有一致） | `/api/user/forgot-password` |
| **Pydantic 模型** | PascalCase + `Response`/`Request` 后缀 | `UserLoginResponse` |

### 14.2 错误码规范

| HTTP 状态码 | 场景 | 响应体 |
|---|---|---|
| 200 | 成功 | 格式 A: `{success: true, data}` / 格式 B: `{code: 200, data, message?}` |
| 400 | 参数错误/业务错误 | `{code: 400, error: "具体错误信息"}` |
| 401 | 未登录/token 过期 | `{code: 401, error: "未登录"}` |
| 403 | 权限不足/IDOR | `{code: 403, error: "权限不足"}` |
| 404 | 资源不存在/stream 过期 | `{code: 404, error: "不存在"}` |
| 429 | 限流/并发超限 | `{code: 429, error: "系统繁忙"}` |
| 500 | 服务器内部错误 | `{code: 500, error: "服务器内部错误"}` |

### 14.3 日志规范

```python
# 结构化日志：所有日志必须包含结构化字段
logger.info("用户登录", user_id=user.id, username=user.username, ip=request.client.host)
logger.warning("Redis 连接断开", error=str(err))
logger.error("Agent 执行失败", user_id=user_id, conversation_id=conv_id, error=str(e))

# 命名 logger：每个模块使用专用 logger
from src.utils.logger import agent_log, stream_log, redis_log, knowledge_log
```

### 14.4 配置管理规范

```python
# 所有环境变量通过 pydantic-settings 统一管理
# src/config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 数据库
    database_url: str = "mysql://root:root@localhost:3306/trip_db"
    
    # JWT
    jwt_secret: str = "change-this"
    jwt_expires_in_days: int = 7
    
    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0
    
    # ChromaDB
    chroma_url: str = "http://localhost:8000"
    
    # LLM
    model_provider: str = "DEEPSEEK"
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = None
    deepseek_model: str | None = None
    
    # CORS
    cors_origin: str = "http://localhost:5173"
    cors_demo: bool = True
    
    # Server
    port: int = 3000
    node_env: str = "development"
    
    # Amap MCP
    amap_maps_api_key: str | None = None
    
    # HF Mirror
    hf_endpoint: str = "https://hf-mirror.com/"
    
    # LangSmith（可选）
    langsmith_api_key: str | None = None
    
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
```

### 14.5 异步规范

- **所有 I/O 密集操作必须 async**：DB 查询、Redis 操作、Chroma 检索、HTTP 调用、LLM 调用
- **同步阻塞调用包装**：sentence-transformers 的 `encode`/`predict` 用 `asyncio.to_thread()` 包装
- **数据库 session**：使用 `async with AsyncSession` 上下文管理，确保连接释放
- **取消传播**：使用 `asyncio.Event` 或 `asyncio.CancelledError` 传播取消信号

### 14.6 序列化规范

- **所有响应模型**继承 `CamelModel`，自动 snake_case → camelCase
- **`_count` 字段**使用 `Field(alias="_count")` 声明
- **分页响应**统一 `{items, total, page, pageSize}` 格式
- **datetime 序列化**：ISO 8601 UTC 格式（与 Node.js `toISOString()` 一致）

---

## 15. 待明确事项

> 注：PRD 第 8 节的 Q1-Q8 已由用户于 2026-07-03 全部确认（见 PRD"已确认决策"表）。以下为架构设计中识别出的工程细节问题，不阻塞开发启动，可在实现过程中逐步明确。

| # | 问题 | 影响 | 当前处理 |
|---|---|---|---|
| 1 | LangSmith 是否需要配置 tracing project？ | 可观测性配置 | 默认不启用，通过 `LANGSMITH_API_KEY` 环境变量开关 |
| 2 | Unsplash API 是否有调用频率限制变化？ | image_fetcher 实现 | 保持现有逻辑，httpx 替代 fetch |
| 3 | 生产环境 worker 数量是否需要调整？ | 性能 | 默认 4，可根据实际负载调整 |
| 4 | 是否需要保留 `feedback-to-fixture` 脚本？ | P2 功能 | 暂缓，后期按需迁移 |
| 5 | MySQL FULLTEXT 索引是否已在现有数据库创建？ | 知识库检索性能 | 迁移后检查 `ft_name_desc` 索引是否存在，不存在则用 LIKE 回退 |
| 6 | 高德 MCP server 的 npm 包版本是否有锁定？ | MCP 子进程启动 | 保持 `npx @amap/amap-maps-mcp-server`，如需锁定版本在 docker-compose 中指定 |

---

> **下一步**：本文档交付开发团队，工程师按第 12 节任务列表（T01-T14）顺序执行。SSE 模块（T09/T10）为最高风险，建议优先完成并在独立分支开发。
