# Trip 后端 Java 重构技术方案（基于 migration-prd-java.md）

> **状态**：草案 v1.0（实施前评审稿）
> **依据**：`docs/migration-prd-java.md`（PRD v1.0）+ Python 端源码精读（orchestrator.py / chat_agent.py / agent_engine.py / rag/ / middleware/ / models/ / services/mcp/ / task_queue.py / stream_store.py / resilience.py / tool_cache.py 等）
> **口径**：功能 1:1 复刻 + 两项设计意图补全（RAG 四路召回+重排、password_resets 建表）；前端零改动、数据零迁移
> **目标栈**：Java 21 + Spring Boot 3.3 + langchain4j 1.x（按需取舍，见 §2.2）

---

## 0. 代码精读关键结论（方案前提）

以下结论直接决定 Java 侧形态，先列出来：

1. **ChatAgent 不是经典多轮 ReAct**：`chat_agent.py` 是"**单次流式 LLM 调用（bind_tools）+ 流式结束后一次性 tool_call 分派**"。流式过程中逐 token 发 `chunk` 事件并累积 `AIMessageChunk`；流结束后从 `raw_msg.tool_calls` 取工具调用逐一分支（trigger_plan / trigger_modify / trigger_patch / select_skill / 其余工具卡片）。**工具结果不二次回注 LLM**。多轮工具循环只存在于 skills 的 `Skill.execute()`（`MAX_SKILL_ITERATIONS=10`）。
2. **Orchestrator 是纯 asyncio 编排**（无 LangGraph）：research → plan → review（`MAX_REVIEW_RETRIES=2`，feedback 注入重跑 Planner）；modify 分局部（target_days 有值，跳过 research，merge 回原行程）与全量两种模式；`validate_with_repair` 兜底。Java 侧按编排语义复刻，**不绑定任何图运行时**（PRD §2.3 已明确）。
3. **事件总线是 `on_event: Callable[[dict], Awaitable]`**：所有阶段（progress/chunk/card/trip_planned/trip_diff/complete/error）都经此回调；controller 层把它接到 SSE 输出 + StreamStore 持久化（双写）。Java 侧需要一个 `EventSink` 接口做同样的事。
4. **Embedding fail-closed**：进程启动即 `mark_embedder_unavailable()`，后台 `load_embedder_force()` 预热成功才恢复向量检索；期间 RAG 走双路（rating + 全文）。Java 侧需保留同一语义（配置开关 + 启动预热任务）。
5. **并发守卫与 token 预算在中间件/依赖层接入**（不在 AgentEngine 内）：`concurrency_guard_dependency`、`token_budget_guard_dependency` 作为 FastAPI Depends 挂在 chat/recommend 路由；SSE 流式端点由流生成器 finally 释放信号量。
6. **Redis 是核心状态层**：限流计数（裸 key=userId/IP，无前缀）、StreamStore（`stream:{uuid}` HASH + `{uuid}:events` LIST + `{uuid}:seq` STRING，TTL 600s、append 续期）、tool_cache（`tool_cache:{tool}:{key}` + `tool_cache_idx:{tool}`）、poi_cache（`poi:{city}:{category}:{query_hash}`，TTL 3600s）、llm_cache（`llm_cache:`，SHA-256 前 32 位，TTL 600s）、research_bundle（`research_bundle:{city}:{budget_tier}:{days}d:{dep}:{interests_hash}`，TTL 300s）。幂等与 MCP 缓存为**进程内存**（多实例不共享，PRD N5）。
7. **RAG 双路（当前基线）**：改写（停用词 + city 前缀）→ rating 排序 + pg 全文（`to_tsvector('chinese', name||' '||description) @@ websearch_to_tsquery('chinese', q)`，失败降级 LIKE）→ 加权 RRF（`weight/(k+rank)`，k=60，pg_fulltext=0.7 / rating=0.5，credibility 乘数 `(0.5+cred)`）→ 截断 limit=5。**四路补全**：新增 spots 向量、spot_docs 向量两路（`1 - (embedding <=> CAST(:vec AS vector))`，`embedding IS NOT NULL`，city/category 过滤），再加 `rerank_with_credibility`（BGE-reranker-base sigmoid 归一化，`final=(1-w)*rerank + w*cred`，w=0.3）。
8. **高德 MCP**：`asyncio.create_subprocess_exec("npx", "-y", "@amap/amap-maps-mcp-server")` + stdio 逐行 JSON-RPC 2.0（`tools/list` 握手探测就绪，10 次 × 1s 超时；`tools/call` 30s 超时）；guards：pybreaker 熔断（fail_max=5, reset 60s）、令牌桶（3/s, capacity 5）、缓存 TTL 1800s（仅 `maps_weather`/`maps_geo` 可缓存）、指标快照（calls/successes/failures/cacheHits/circuitOpenCount/avgDurationMs）。
9. **任务队列**：arq（Redis）双后端 + asyncio 内存降级；7 个 worker（embedding_sync×2、post_chat_followup、fetch_city_wiki、demo×3）；`max_tries=3`（退避 1/2/4s）、job_timeout=300s、keep_result 3600s、**job_id 即幂等键**。降级路径构造 fake_ctx 同签名调用。
10. **异常映射不对称**：auth/限流/守卫抛的 `HTTPException` 走 FastAPI 默认 `{"detail":...}` 包装；业务 `AppException` 走 Format A/B（`/api/trip/recommend` 前缀判定）；JWT 缺头 403 / 坏 token 401（HTTPBearer 默认）。IntegrityError → 409 DUPLICATE_ENTRY / 400 FOREIGN_KEY_VIOLATION / 400 INTEGRITY_ERROR。

---

## 1. 技术选型表

> 原则：**能自研就自研（语义复刻优先），能复用生态就复用（但不被框架语义绑架）**。PRD R2/R4 已明确"按编排语义而非 API 形态复刻"、"向量走原生 SQL"。

| # | Python 组件（文件） | Java 对应方案 | 说明 |
|---|---|---|---|
| 1 | FastAPI + uvicorn（main.py） | **Spring Boot 3.3（WebMVC）+ 虚拟线程** | SSE 手动写帧（见 §2.1）；不用 WebFlux（理由见取舍 T1） |
| 2 | SQLAlchemy async + asyncpg（config/database.py） | **Spring Data JPA（Hibernate 6.x）+ JdbcTemplate 双轨** | JPA 管标量 CRUD；向量/全文/聚合走 JdbcTemplate 原生 SQL（R4） |
| 3 | pgvector + HNSW（models/spot.py, spot_doc.py） | **原生 SQL**：`1 - (embedding <=> CAST(:vec AS vector))`，HNSW 索引复用 | JPA 实体 `@Transient` 跳过 embedding 列 |
| 4 | JSONB 列（users.preferences、messages.metadata、trips.content、spots.tags） | **Hibernate `@JdbcTypeCode(SqlTypes.JSON)` + Jackson** | 往返序列化测试对齐（验收 1.2） |
| 5 | redis-py async（config/redis_client.py） | **Spring Data Redis（Lettuce）** | 仅用低级命令（INCR/EXPIRE/HSET/LRANGE/SETEX/RPUSH），语义自控 |
| 6 | LangChain `ChatOpenAI` streaming（config/llm.py） | **langchain4j 1.x `OpenAiStreamingChatModel`（OpenAI 兼容协议）** 或自研协议层 | 见取舍 T2；DeepSeek/Kimi/Agnese 均为 OpenAI 兼容 |
| 7 | `bind_tools` + tool_calls delta + `stream_options.include_usage` | **自研 OpenAI 流式解析**（ToolCallDelta 累积 + usage 末帧提取） | 这是 R2 高风险点，spike 先行 |
| 8 | Orchestrator / ResearchAgent / PlannerAgent / review（services/agent/） | **自研编排组件**（`Orchestrator`/`ResearchAgent`/`PlannerAgent`/`ReviewService`） | 不绑定 langchain4j AiServices / 图运行时 |
| 9 | ChatAgent（agents/chat_agent.py） | **自研 `ChatAgent`**：EventSink + 工具分派器 | 单次流式 + 流后分派语义复刻 |
| 10 | AgentEngine 单例（agent_engine.py） | **Spring 单例 `AgentEngine`**（@Component，懒初始化共享 llm/tool_cache/skill_registry） | chat()/recommend() 两链路 |
| 11 | JWT（utils/security.py） | **jjwt 0.12.x** | HS256、7 天、payload `{userId,username,roleId,exp}`，只强校验 userId+exp |
| 12 | bcrypt rounds=12（utils/security.py） | **jBCrypt**（`BCrypt.gensalt(12)`） | 需验证与现有密码哈希互认（验收 2.1） |
| 13 | 限流 6 实例（middleware/rate_limiter.py） | **自研 `RateLimiter`（固定窗口，Redis INCR+EXPIRE 降级内存）** | 6 实例阈值/窗口/响应头（X-RateLimit-Reset 绝对时间戳）逐一复刻 |
| 14 | 幂等中间件（middleware/idempotency.py） | **自研 `IdempotencyMiddleware`（进程内存 TTL Map）** | 仅 `/api/trip/recommend`；key=`{userId或anonymous}:{key}`，TTL 3600s，只缓存 2xx JSON |
| 15 | 并发守卫（middleware/concurrency_guard.py + semaphore.py） | **自研 `ConcurrencyGuard`（`Semaphore(10)` + per-user `Semaphore(1)`）** | 非阻塞获取，429；SSE 流 finally 释放 |
| 16 | Token 预算（middleware/token_budget_guard.py + token_budget.py） | **自研 `TokenBudgetManager`（固定窗口滑动重置）** | 用户 50K/h → 429；全局 200K/min → 503 |
| 17 | Token 记账（token_tracker.py + token_monitor.py） | **自研 `TokenTrackingCallback` + `TokenMonitor`** | 环形缓冲 1000 条、单次 >100K 告警、落库 token_usage_logs |
| 18 | Prometheus（middleware/prom_metrics.py） | **Micrometer + `prometheus-registry`** | 4 类指标名/label/bucket 对齐（0.005–10s、0.1–60s buckets） |
| 19 | structlog + x-request-id（main.py RequestIDMiddleware） | **Logback + MDC** | x-request-id 透传/回写/日志贯穿（验收 1.8） |
| 20 | arq 任务队列（task_queue.py + worker.py） | **自研 `TaskQueue`：Redis List 队列 + @Scheduled 消费（内存 @Async 降级）** | job_id 幂等、max_tries=3 退避 1/2/4s、job_timeout 300s、keep_result 3600s |
| 21 | Embedding：bge-small-zh-v1.5（rag/embeddings.py） | **ONNX Runtime（首选）或旁路 Python 服务（备选）** | 见取舍 T4；fail-closed + 预热 + 余弦一致性回归 |
| 22 | Reranker：BGE-reranker-base（rag/reranker.py） | **ONNX Runtime CrossEncoder + sigmoid** | 不可用降级原始顺序 |
| 23 | RAG 检索链（rag/*.py） | **自研 `RetrievalPipeline`（四路召回 → 加权 RRF → credibility 重排 → 截断）** | SQL 逐字复用，降级链保留 |
| 24 | 高德 MCP（services/mcp/） | **`ProcessBuilder` spawn npx + 手写 JSON-RPC 2.0（Jackson）** | 握手/就绪探测/guards/指标复刻；见取舍 T7 |
| 25 | 缓存（tool_cache.py / poi_cache.py / llm_cache.py / research_bundle_cache.py） | **自研双后端缓存组件（Redis 优先 + 内存降级）** | key 格式、TTL、embedding 相似度命中 ≥0.85 逐一对齐 |
| 26 | 技能系统（skills/） | **自研 `SkillRegistry`（L1/L2/L3 + select_skill + MAX_SKILL_ITERATIONS=10）** | 读取 `.claude/skills` 目录 |
| 27 | 告警系统（services/alert/） | **@Scheduled + 自研 AlertDetector/Deduplicator/Webhook** | 300s 周期、60min 窗口、满意率公式、MD5 去重 3600s、5 种 payload |
| 28 | provider 路由与健康（provider_router/） | **自研 `ProviderRouter` + `ProviderHealthRegistry`** | 3/5 次失败降级、60s 恢复、场景优先级表、15s failover |
| 29 | 美团 CLI（tools/meituan.py） | **ProcessBuilder 调 `npx @meituan-travel/ht-ai`（沙箱列表传参）** | 150s 超时、无 shell、MEITUAN_HT_TOKEN 校验 |
| 30 | SSE（utils/stream.py + stream_store.py） | **手写 SSE 帧输出（HttpServletResponse 流）+ 自研 `StreamStore`** | 见取舍 T6 |
| 31 | /health、/health/detail、/metrics | **Spring Actuator 自定义端点** | 语义保留（PlainText "OK"、detail JSON 结构） |
| 32 | docker-compose（app/postgres+pgvector/redis） | **docker-compose 等价编排** | Java 服务 + 复用现有 PG/Redis |

---

## 2. 关键设计取舍

> 每个取舍给 2-3 个选项 + 推荐。序号与 §1 对应。

### T1. Web 层形态：WebFlux vs WebMVC+虚拟线程 vs WebMVC+平台线程

| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. Spring WebFlux（Flux\<ServerSentEvent\>）** | SSE 原生支持、非阻塞、背压语义好 | 与命令式编排代码割裂；调试/监控栈不同；Python asyncio 语义映射不直观；工具链（DB/Redis 阻塞调用）需全链路 reactive |
| **B. WebMVC + 虚拟线程（推荐）** | 命令式代码与 Python 1:1 映射；虚拟线程支撑高并发（登录 QPS≥6.0 轻松满足）；SSE 手动写帧完全控制格式与 flush 时机；与 R1"不缓冲"约束天然契合 | SSE 需自行管理线程安全（事件缓冲用同步队列）；虚拟线程对阻塞 IO 友好（DB/Redis/子进程皆可阻塞） |
| C. WebMVC + 平台线程 | 最简单 | 线程池上限限制并发（全局 10 并发守卫下够用，但未来扩展受限） |

**推荐 B**：SSE 是核心协议面（12 类事件 + 帧格式 + 心跳 + 续传），手动写帧最可控；编排逻辑全部命令式，与 Python 结构逐行对应；虚拟线程成本为零。SSE 输出用 `HttpServletResponse` + 同步 `OutputStream`（每次事件后 `flush()`），事件源用 `BlockingQueue` + 心跳调度器，客户端断开通过 `onError`/`onDisconnect` 回调回收（释放并发信号量）。

### T2. LLM 接入层：langchain4j 全栈 vs langchain4j 协议 + 自研编排 vs 自研 OpenAI 客户端

| 选项 | 优点 | 缺点 |
|---|---|---|
| A. langchain4j 全栈（AiServices + ToolSpecification + TokenStream） | 少写代码；工具 schema 自动生成 | AiServices 的编排模型（@Tool 方法注入、自动 tool loop）与 Python 的"单次流式+流后分派"不匹配；流式 tool_calls delta 与 `include_usage` 末帧提取在 1.x 覆盖不全（PRD R2 点名） |
| **B. langchain4j 仅做模型协议封装，编排全自研（推荐）** | 复用 `OpenAiStreamingChatModel`（OpenAI 兼容：DeepSeek/Kimi/Agnese 通用）；`ToolSpecification.fromJsonSchema` 生成工具 schema；流式回调自定义（`onPartialResponse`/`onToolExecuted`）；`ChatResponse` usage 可提取 | 需要先 spike 验证 langchain4j 对"流式中累积 tool_calls + 末帧 usage"的暴露能力；不满足处用原生 HTTP 兜底 |
| C. 完全自研 OpenAI 兼容客户端（OkHttp/WebClient + Jackson） | 协议 100% 可控（含 `stream_options.include_usage`、tool_calls delta、reasoning_content） | 全部自己写（重试/超时/SSE 解析），工作量大 |

**推荐 B（含 C 的关键点）**：**先做 1-2 天 spike**：用 langchain4j 1.x 对三个 provider 发流式工具调用请求，验证 (a) 流式过程中 tool_calls 增量能否累积出完整工具调用；(b) 末帧 usage（含 cachedTokens）能否取出；(c) 中文 tools schema（description 字段）能否正确下发。spike 不过的部分（极可能是 usage/cached 与 tool_call delta），降级为自研协议层（方案 C），编排层无论如何自研。LLM 相关请求统一收敛在 `LlmGateway`（§3.1），后续替换实现不影响上层。

### T3. 任务队列：自研 Redis 队列 vs 现成任务框架（Quartz/SI/Redisson）vs @Async 内存

| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. 自研轻量 Redis List 队列（推荐）** | 语义与 arq 完全对齐：job_id 幂等（`SETNX arq:job:{id}` 或等价键）、max_tries=3 退避 1/2/4s、结果 JSON 存 Redis TTL 3600s、Redis 不可用降级 @Async 内存（fake_ctx 等价物）；key 前缀与 Python 可对照 | 需要自己处理 worker 消费循环与崩溃重试（单实例 @Scheduled 即可，PRD N5 不做多实例） |
| B. Spring Integration / Quartz / Redisson 队列 | 现成组件 | 语义与 arq 不匹配（重试退避、幂等键、结果 TTL、keep_result 都要二次定制）；引入重依赖 |
| C. 纯 @Async 内存 | 零依赖 | 无重试/幂等/结果存储，无法满足验收 6.4（Redis 不可用→内存降级）与任务测试 |

**推荐 A**：7 个 worker（`embedding_sync`×2、`post_chat_followup`、`fetch_city_wiki`、`demo`×3）都是短任务、单实例消费；Redis 双后端（LPUSH/BRPOP + 结果 SETEX）+ 内存降级足够。幂等键直接用 job_id（如 `post_chat:followup:{conversation_id}`），与 Python 相同字符串，便于对拍。

### T4. Embedding 模型加载：ONNX Runtime vs 旁路 Python 服务 vs DJL/PyTorch

> 硬约束：现有库已写入的向量由 bge-small-zh-v1.5（sentence-transformers）产出，Java 侧必须产出**同语义向量**（检索质量不漂移，PRD G6/R3）。

| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. ONNX Runtime 导出（首选）** | 离线、无新服务依赖、推理快（CPU 足够）；`transformers.onnx` 导出后与 HF 权重位级一致（float32）；tokenizer（WordPiece）手写或借用 `transformers` tokenizer.json 转换 | 需做 ONNX 导出与 tokenizer 移植（一次性工作量，约 1-2 人日）；须用**余弦一致性回归**（抽样现有库 embedding 对比 ≥0.999）把关 |
| B. 旁路 Python embedding 微服务 | 语义 100% 一致、零漂移；实现最快 | 新增一个运行依赖，与"单 Java 服务"部署意图冲突；故障面扩大（PRD 部署仍为三服务） |
| C. DJL 加载 PyTorch 模型 | Java 生态内 | sentence-transformers 的 mean pooling + L2 normalize 需手写复刻；DJL 对 PyTorch 模型要求原生库，部署成本高；精度对齐风险同 A 但工具链更生僻 |

**推荐 A（保留 B 作为回退项）**：选 A 时注意三点——(1) 查询前缀 `"为这个句子生成表示以用于检索相关文章："` 必须在 Java 侧逐字保留（`embeddings.py L83`）；(2) `normalize_embeddings=True`（L2 归一化）必须复刻（查询与文档两侧都要）；(3) batch_size=32、40s 超时、fail-closed + 后台预热语义保留。选 B 时通过 HTTP 暴露 `/embed`，Java 侧只做客户端封装，其余降级逻辑不变。**放行条件：抽样 50 条现有 `spots.embedding` 与 Java 复算向量的余弦相似度 ≥0.999，且 Hit@K/MRR 不低于基线。**

### T5. 数据层：JPA 全量映射 vs JPA(标量)+JdbcTemplate(向量/全文) 混合

| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. 混合（推荐）** | JPA 管 CRUD 开发效率高；向量/全文/聚合/`\d` 兼容问题全部收敛在原生 SQL 层（R4）；HNSW 索引与 pgvector 扩展零接触 | 两套访问路径需约定边界（实体只映射标量列） |
| B. JPA 全量（含 vector 自定义 Hibernate 类型） | 单一路径 | Hibernate 对 `vector(512)` 的类型映射需自写 UserType，HNSW 索引创建/校验易出问题；`websearch_to_tsquery('chinese',...)` 这类函数查询 JPA 表达困难 |
| C. 纯 JdbcTemplate | 无 ORM 阻抗 | 12 张表 CRUD 全手写，开发量大且易错（分页、upsert、关系） |

**推荐 A**：`ddl-auto=none`（或 `validate` 仅对 password_resets 特例——见 §4.4），实体 `@Transient` 跳过 embedding；JSONB 用 `@JdbcTypeCode(SqlTypes.JSON)`；全文/向量/RRF 全部 `NamedParameterJdbcTemplate` 原生 SQL，**SQL 文本与 Python 逐字一致**（R5）。

### T6. SSE 输出：手动写帧 vs SseEmitter vs Flux

| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. 手动写帧（推荐）** | 帧格式 100% 可控（`id: {seq}\nevent: {type}\ndata: {json}\n\n`、无 id/无 type 的特殊帧、`X-Accel-Buffering: no`）；心跳（15s/3s）与续传重放直接内联；天然规避 GZip/框架缓冲（R1） | 需自己处理客户端断开（`onError`/`onDisconnect`）与写并发 |
| B. SseEmitter | Spring 原生、生命周期管理好 | 帧格式由 Spring 序列化，`id/event/data` 定制有约束；心跳需自建调度；与续传重放（保留原 seq）配合别扭 |
| C. Flux\<ServerSentEvent\> | 声明式 | 绑定 WebFlux（见 T1） |

**推荐 A**：输出器 `SseWriter` 封装一个线程安全的"帧队列"，业务线程 `offer`、IO 线程（虚拟线程）消费并 `flush()`；断开时通过回调触发"流结束清理"（并发信号量释放 + StreamStore markComplete + 消息强制 flush）。**GZip 中间件对 SSE 路径直接跳过**（response header 检测或路径白名单）。

### T7. 高德 MCP：ProcessBuilder 直连 vs 现成 MCP Java SDK（modelcontextprotocol/java-sdk）

| 选项 | 优点 | 缺点 |
|---|---|---|
| A. modelcontextprotocol/java-sdk | 协议栈现成（stdio transport、JSON-RPC） | SDK 较新、版本演进快；与 Python 侧"npx + tools/list 握手探测"的时序细节（10×1s、id=0 探测）需要二次定制；guards（熔断/令牌桶/缓存）无论如何自研 |
| **B. ProcessBuilder + 手写 JSON-RPC 2.0（推荐）** | 完全复刻 Python 行为：spawn `npx -y @amap/amap-maps-mcp-server`、注入 `AMAP_MAPS_API_KEY`/`AMAP_KEY` 环境变量、`tools/list` 轮询握手（10 次 × 1s）、`tools/call` 30s 超时、stderr 读取防阻塞；无新增依赖 | JSON-RPC 解析自己写（Jackson 即可，~200 行） |

**推荐 B**：协议面很小（initialize 可由 tools/list 替代、无通知订阅需求），自研成本低且行为可对拍；guards 层（`MCPCircuitBreaker` fail_max=5/reset 60s、`MCPRateLimiter` 令牌桶 3/s capacity 5、`MCPCache` TTL 1800s 仅 weather/geo、`MCPMetrics` 快照）按 Python 语义独立实现。子进程生命周期（启动/就绪/熔断/重启）纳入冒烟与指标测试（验收 6.3）。

### T8. 限流/幂等/并发守卫的实现位置：Filter 链 vs AOP vs 框架内置

| 选项 | 优点 | 缺点 |
|---|---|---|
| **A. 自研 OncePerRequestFilter 链（推荐）** | 与 Python 中间件链顺序一一对应（Prometheus→RequestID→Idempotency→GlobalRateLimit→CORS→GZip→路由）；固定窗口、INCR+EXPIRE、内存降级全部自控 | 需自行维护过滤器顺序与路径白名单 |
| B. Spring 内置限流（Bucket4j/Resilience4j） | 现成算法 | 窗口算法/响应头/降级语义与 Python 不一致，需大量适配 |
| C. AOP 注解 | 声明式 | 与 Python"中间件链 + Depends 注入"的形态差异大；SSE 流式释放语义（finally）难表达 |

**推荐 A**：中间件链顺序、路径约束（幂等仅 `/api/trip/recommend`；chat/recommend 挂并发+预算守卫；`{"detail"}` 包装例外）全部显式配置，逐个对应 PRD 验收 1.4/1.5/1.6。

---

## 3. 核心类设计

> 包结构建议：`com.trip.backend` 下 `web/`（controller+filter+sse）、`service/`（业务+agent+rag+mcp+task）、`domain/`（entity+repository）、`infra/`（redis、cache、llm、metrics、security）。本节只列关键类签名与行为要点，字段级细节以源码为准。

### 3.1 LLM Gateway（对应 config/llm.py + provider_router/ + token_tracker.py + token_budget.py）

```
LlmGateway (Spring 单例)
├── ProviderRegistry: Map<ProviderId, ProviderConfig>   // deepseek/kimi/agnese: baseUrl+model+apiKey
├── ProviderHealthRegistry: Map<ProviderId, HealthState>
│     // HEALTHY/DEGRADED/DOWN；consecutiveFailures>=3→DEGRADED, >=5→DOWN；60s 自动恢复(→DEGRADED)
├── ScenarioPriority: PLANNING=[deepseek,kimi,agnese] / CHAT=[agnese,kimi,deepseek] / RESEARCH=[agnese,deepseek,kimi]
├── callWithFallback(scenario, fn, fallbackFn, timeout=15s)   // 超时记失败→切 fallback；fallback 无超时保护
└── createModel(provider, streaming): LlmClient               // OpenAI 兼容协议封装

LlmClient (接口，spike 后落定实现)
├── stream(List<ChatMessage> messages, List<ToolSpec> tools, StreamSink sink) → ChatResponse
│     // sink 回调: onTextChunk(String) / onToolCallDelta(ToolCallDelta) / onUsage(TokenUsage)
├── invoke(...) → ChatResponse                                // 非流式（planner fallback、review LLM、偏好提取）

TokenTracking (复刻 token_tracker.py)
├── LlmContext: ThreadLocal<{userId, endpoint}>               // LLMContext 上下文管理器等价物
├── TokenMonitor: 环形缓冲(1000) + 单次>100K 告警 + 落库 token_usage_logs
└── TokenBudgetManager: 用户 50K/h(429) + 全局 200K/min(503)   // 固定窗口，resetAt 惰性重置
```

行为要点：
- **usage 提取**：`cached` 兼容 `promptCacheHitTokens` / `prompt_cache_hit_tokens` / `promptTokensDetails.cachedTokens`；`prompt+completion<=0` 跳过记账。
- `on_llm_end` 记账是 fire-and-forget（异步写 DB + 更新预算），不阻塞主链路。
- 场景路由：ChatAgent 用 CHAT 优先级、Orchestrator.research 用 RESEARCH、planner 用 PLANNING（主 LLM 失败切 fallback_llm）。

### 3.2 Orchestrator（对应 orchestrator.py + research_agent.py + planner_agent.py + review.py）

```
Orchestrator(llm, fallbackLlm, EventSink onEvent)
├── plan(PlanRequest) → PlanResult
│     // 1. research: 并行 5 工具 → ResearchBundle（progress research start/done）
│     // 2. plan: PlannerAgent.run → raw_output（progress plan start/done）
│     // 3. review 循环: for attempt in 0..MAX_REVIEW_RETRIES(2):
│     //       review(raw, bundle, budget, days) → (parsed, ReviewResult)
│     //       passed → break; 否则 planner_input.feedback=review.feedback 重跑
│     // 汇总 usage（prompt/completion/total/cached 四键逐项相加）
├── modify(existingTrip, modifyRequest, PlanRequest, targetDays?) → PlanResult
│     // is_partial = targetDays 非空：跳过 research（skipped=true 事件）、
│     //   planner 只输出修改天 → _mergePartialPlan 回原行程（按 day 替换 + budgetBreakdown 增量重算）→ review
│     // 全量模式：完整 research+plan+review
└── _mergePartialPlan / _parseJsonSafe(repair) / _extractInterests   // 静态工具，语义照搬

ResearchAgent → 并行 5 工具(attractions/food/hotels/weather/distance) → ResearchBundle
PlannerAgent → 主 LLM 失败切换 fallback_llm；输出 raw_output
ReviewService → 纯校验链：
  JSON 解析(repair_json) → 天数一致(target_days 局部模式跳过) → 预算≤1.15× →
  budgetBreakdown 五键(accommodation/food/transportation/tickets/other) → 候选池封闭世界
  (bundle.all_spot_names 差集) → LLM 二层审阅(仅前 3 天、截断 2000 字符、warning 不强制打回)
```

### 3.3 ChatAgent 流式双流（对应 chat_agent.py + agent_engine.py）

"双流"指两条并行输出通道：**① SSE 事件流**（chunk/card/progress/trip_planned/trip_diff/complete/error + StreamStore 持久化）；**② LLM 流式输出与工具调用分派**（流中累积、流后分派）。

```
ChatAgent(llm, EventSink onEvent, systemPrompt, userId, tripMeta?)
└── run(message, history, tripContext) → AgentOutput{result, usage, durationMs}
    1. 拼 system prompt（trip_context → 追加 "# 用户当前行程" + "# 行中伴随能力" 四段）
    2. 消息组装: [system] + history(human/ai) + [human]
    3. 延迟加载 9+3 工具（含 amap 前 3 个，失败静默）
    4. LLM 前预检测 _tryPreLlmTool(message)：
       // nearby_kw={附近,周边,周围,旁边}、commute_kw={怎么走,怎么去,通勤,路线,过去,坐车,打车,最快}
       // 命中 → 直调 commute_service（绕过 resilience/tool_cache）→ 发 card → 结果注入 system prompt
    5. streamLLM(messages, timeout=60s)：
       // 逐 chunk: onEvent({type:chunk, content})；累积 AIMessage（含 tool_calls delta）
       // 末帧提取 usage（input/output/total）
    6. 流结束 → 若 rawMsg.toolCalls 非空，逐一按 name 分派：
       trigger_plan   → Orchestrator.plan → TripService.persist(status=completed) → trip_planned 事件
       trigger_modify → Orchestrator.modify → persist(parent_trip_id, status=candidate) → trip_diff 事件
       trigger_patch  → patchEngine.applyPatch → persist(candidate) → trip_diff；
                        PatchError/任意异常 → 降级 _escalateModify（modify_request=“第X天Y更换为Z”, target_days=X）
       select_skill   → SkillRegistry.execute（注入 6 底层工具 + meituan_query_tool）
       其他           → _executeToolCard（search_commute_tips 特判：先取坐标、_isNearbyQuery 则自动 POI 搜索；
                         POI→poi_list card；通勤→commute_compare card；其余→info_text card ≤1500 字）
    7. 无 tool_calls → 直接返回 content

AgentEngine（Spring 单例）
├── chat(userId, message, conversationId, onEvent, messageId, tripContext, tripId)
│     // ensureAmapTools → loadPreferences → loadContext(摘要/脉络/近期消息) →
│     // buildSystemPrompt(含 L1 技能目录) → TraceRecorder(messageId) → ChatAgent.run
│     // 成功: trace.add(complete)+flush → tokenMonitor.record(异步) → onEvent(complete{content,usage})
│     // 异常: trace.add(error)+flush → onEvent(error) → rethrow
└── recommend(userId, city, budget, days, departureCity, conversationId, onEvent, messageId)
      // 并行 ensureAmapTools+loadPreferences → fallbackLlm → Orchestrator.plan
      // plan 无效时 validateWithRepair 兜底 → 仍失败 raise "Agent 多次输出无效 JSON"
```

补全细节（Java 必须复刻的"隐性"行为）：
- `_merge_usage`：四键逐项相加。
- `_escalate_plan`：`user_id<=0` 时从 trip_meta 兜底；无有效 user_id 不落库只回 JSON。
- `_escalate_modify`：无 trip_meta → 固定文案"当前没有关联行程，无法修改。请先在行程详情页打开对话。"；落库失败 → 友好文案不抛 SQL 错误。
- `_build_trip_diff`：按 day→morning/afternoon/evening 比对 spot，输出 `{day, period, oldSpot, newSpot}`（空值用 "(无)"）。
- 卡片事件结构：info_text `{title, content≤1500}`；poi_list `{items≤10}`（name/distance/rating/cost）；commute_compare `{options≤5, recommended:0}`（mode_label 映射、duration_text/duration_sec//60 分钟、distance_text/distance_m/1000 km）。

### 3.4 StreamStore 断点续传（对应 stream_store.py）

```
StreamStore
├── createStream(userId, conversationId) → {streamId, seq:0}
│     // Redis: HSET stream:{uuid} {userId,conversationId,status:active,createdAt,lastEventAt} + SET seq=0 + EXPIRE 600
│     // 内存降级: _InMemoryStream 等价结构
├── appendEvent(streamId, eventType, eventData) → seq
│     // 单事件 ≤64KB（超限抛 ValueError）；INCR seq → RPUSH {id}:events → HSET lastEventAt → EXPIRE 续期 ×3
├── getEventsSince(streamId, lastSeq) → List<StreamEvent>
│     // lastSeq > totalSeq → 400；lastSeq >= totalSeq → 空；LRANGE {id}:events lastSeq -1
├── getStreamState(streamId) → StreamState   // IDOR 校验用（userId 比对 → 不匹配 403）
├── markComplete / deleteStream / cleanupExpired(24h)
└── 全部方法 Redis 不可用时自动落内存实现

SseResumeFilter / ResumeHandler
// X-Stream-Id + Last-Event-ID 同时存在才触发；重发 seq>lastSeq 全部事件（保留原 id）并追加 end；
// 只读重放不改状态；错误映射：400 非法/超界、404 不存在/过期、403 owner 不匹配
```

### 3.5 RAG 召回-融合-重排（对应 rag/ 全部）

```
RetrievalPipeline (Spring 单例)
└── search(query, city, category?, limit=5) → List<SpotHit>
    1. QueryRewriter.rewrite: 清洗(去标点) → extractKeywords(停用词 zh/en + len>=2 + 去重) → 拼 city 前缀
    2. 四路召回（并发执行，各自 try/catch 返回 []）:
       - ratingSearch:     SELECT ... ORDER BY rating DESC NULLS LAST LIMIT :limit   (_source=rating)
       - fulltextSearch:   to_tsvector('chinese', coalesce(name,'')||' '||coalesce(description,''))
                           @@ websearch_to_tsquery('chinese', :q)  ORDER BY rating DESC   (失败→LIKE 降级)
       - vectorSearchSpots:    1-(embedding<=>CAST(:vec AS vector)) AS score, embedding IS NOT NULL,
                               city/category 过滤, ORDER BY embedding<=>:vec   (_source=pgvector)
       - vectorSearchSpotDocs: JOIN spots ON sd.spot_id=s.id WHERE sd.embedding IS NOT NULL AND s.city=:city
                               ORDER BY sd.embedding<=>:vec                        (失败→全文聚合/跳过)
    3. 加权 RRF（rrfMergeWithWeights）: score += weight/(k+rank), k=60,
       权重: pg_fulltext=0.7, rating=0.5, spots_vec=W1, spot_docs_vec=W2（W1/W2 配置项，回归调优）,
       scoreAdjuster = weight_by_credibility: 贡献 ×(0.5+cred)   // 加权失败降级普通 RRF
    4. credibility 重排（rerankWithCredibility）:
       - ONNX CrossEncoder(bge-reranker-base) 对 (query, doc) 打分 → sigmoid 归一化
       - final = 0.7*rerankScore + 0.3*credibilityScore
       - 模型不可用/失败 → 保持 RRF 顺序（分数 0）
    5. 截断 limit=5 返回
降级链（保留）: embedding 不可用 → 跳过两路向量 → 全文失败 → LIKE → RRF 加权失败 → 普通 RRF
               → rerank 不可用 → 原始顺序；检索链路始终可用

Embedder (fail-closed)
├── markUnavailable()  // 启动即调用（AgentEngine 构造时）
├── warmup()           // 后台一次性任务，成功才清 fail-closed
└── embed(query|docs)  // 查询前缀 + L2 normalize；40s 超时；batch=32
Reranker: load 失败降级原始顺序（与 Python `_TORCH_AVAILABLE=False` 分支等价）
```

SQL 注意点（与 Python 逐字一致，R5）：`CAST(:vec AS vector)` 不能写成 `:vec::vector`（SQLAlchemy 绑定参数冲突问题在 JDBC 侧同样存在，`CAST` 是安全写法）；全文 `'chinese'` 配置（COPY=simple）直接复用，不做"改进"。

---

## 4. 数据兼容方案

### 4.1 总体策略

- **直连现有 PG 16**：`ddl-auto=none`，绝不由 Hibernate 改表；启动时做"12 表齐全校验"（`information_schema.tables` 查询），缺失表（仅 `password_resets` 预期）幂等补建（§4.4）。
- **索引零改动复用**：`idx_spots_embedding_hnsw`（m=16, ef_construction=64, cosine）、`idx_spot_docs_embedding_hnsw` 同参数、`idx_spots_city_category`、`idx_messages_conv_created` 等全部沿用现有。
- **连接池**：HikariCP，与 Python 对齐"池 10/溢出 20"（`maximum-pool-size=10`，Python `pool_size=10, max_overflow=20` 的语义近似为 10+20 借出上限，实施时按验收 1.1 对拍调整）。

### 4.2 12 张表 JPA 映射

| 表 | 实体 | 关键字段/约束 | JSONB 处理 |
|---|---|---|---|
| roles | Role | id, name(enum ADMIN/USER, unique) | — |
| users | User | username/email unique, password(255), role_id FK→roles, status, **preferences** | `@JdbcTypeCode(SqlTypes.JSON)` |
| password_resets | PasswordReset | email, token unique, expires_at(tz), used(bool)；无 updated_at | — |
| trips | Trip | user_id FK, from_city, city, days, budget, **content**, status(default completed), parent_trip_id 自引用；**无 updated_at** | content JSON |
| conversations | Conversation | user_id FK, title, summary, recap, summary_error, summary_at；有 updated_at | — |
| messages | Message | conversation_id FK **ondelete CASCADE**, role, content Text, **metadata**, excluded_from_context；无 updated_at；索引 (conversation_id,created_at)、(conversation_id,excluded_from_context) | metadata JSON |
| spots | Spot | name/city/category/description, **tags**, avg_cost, duration, open_time, rating, **embedding Vector(512)**；索引 (city,category)+HNSW | tags JSON；embedding `@Transient` |
| spot_docs | SpotDoc | spot_id FK→spots, source_type/source_name/source_url/title/content/chunk_index, **embedding Vector(512)**, authority_score/freshness_score/agreement_score/citation_count/evidence_density/credibility_score, published_at/retrieved_at；索引 source_type+HNSW | embedding `@Transient` |
| feedbacks | Feedback | user_id FK, message_id FK **CASCADE**, conversation_id, rating(1/-1), comment(500), tags；唯一约束 (user_id,message_id)；索引 message_id/(rating,created_at)/(user_id,created_at) | tags JSON |
| agent_steps | AgentStep | message_id FK **CASCADE**, step, type, name, args, output, duration_ms, error；索引 (message_id,step)；无 updated_at | args JSON |
| token_usage_logs | TokenUsageLog | user_id FK **CASCADE**, request_type, route, conversation_id FK **SET NULL**, message_id FK **SET NULL**, prompt_tokens/completion_tokens/total_tokens/cached_tokens, latency_ms；索引 (user_id,created_at)、request_type | — |

共 **12 张表**（PRD 口径；不含任何中间表）。所有 `updated_at` 可空列、`DateTime(timezone=True)` 映射为 `OffsetDateTime`。

### 4.3 vector 列处理（R4）

- 实体层：`@Transient` 跳过（JPA 不读写 embedding 列）。
- 检索/写入：全部 `NamedParameterJdbcTemplate` 原生 SQL：
  - 查询：`1 - (embedding <=> CAST(:vec AS vector)) AS score`（`:vec` 为 `[0.1,0.2,...]` 字符串）；
  - 写入（embedding_sync 任务）：`UPDATE spots SET embedding = CAST(:vec AS vector) WHERE id = :id`；
  - 更新时显式 `embedding IS NOT NULL` 过滤语义保留（Python 侧检索条件）。
- 512 维校验：写入前断言长度=512（与 `Vector(512)` 一致），非法向量由任务层拒绝。

### 4.4 password_resets 补建（R14）

- 启动校验：查询 `information_schema.tables`；缺表执行幂等 DDL（`CREATE TABLE IF NOT EXISTS password_resets (...)`），字段与 `models/password_reset.py` 一致：
  `id serial PK, email varchar(100) not null, token varchar(255) not null unique, expires_at timestamptz not null, used boolean not null default false, created_at timestamptz not null`。
- 对现有库为幂等 no-op（验收 1.9：前后数据行数不变）；对空库自动补建。**不触碰其余 11 张表**。
- 实施前先实测现有库该表状态（可能已存在但 DDL 不同 → 只读不覆盖，仅校验所需字段存在）。

### 4.5 JSONB 与序列化兼容

- `@JdbcTypeCode(SqlTypes.JSON)` 由 Hibernate 6 用 Jackson 序列化/反序列化，与 Python `JSON` 列（SQLAlchemy 存 JSON 文本）读写互认（PG jsonb 规范化存储，无兼容风险）。
- 序列化细节：`ensure_ascii=False`（Python 侧所有 json.dumps 均 UTF-8 直出）——Jackson 默认即 UTF-8，注意**不要**开启 `ESCAPE_NON_ASCII`。
- 往返测试（验收 1.2）：preferences/metadata/content/tags 各写一读一，断言结构等值（含嵌套中文、空数组、null）。

### 4.6 Redis key 兼容清单

| 用途 | key 格式 | TTL | 后端 |
|---|---|---|---|
| 限流计数 | `{userId 或 IP}`（无前缀） | 窗口秒 | Redis/内存 |
| StreamStore | `stream:{uuid}` HASH；`stream:{uuid}:events` LIST；`stream:{uuid}:seq` STRING | 600s，append 续期 | Redis/内存 |
| tool_cache | `tool_cache:{tool}:{literalKey}`；embedding 模式 `tool_cache:{tool}:embed:{text}`；索引 `tool_cache_idx:{tool}` | 300–3600s（per-tool） | Redis/内存 |
| poi_cache | `poi:{city}:{category}:{queryHash}` | 3600s | Redis/内存 |
| llm_cache | `llm_cache:{sha256(prompt)[:32]}` | 600s | Redis/内存 |
| research_bundle | `research_bundle:{city}:{budget_tier}:{days}d:{dep}:{interestsHash}` | 300s | Redis/内存 |
| arq 任务结果 | `arq:result:{job_id}`（自研时可用同前缀，便于对拍） | 3600s | Redis/内存 |

---

## 5. 迁移顺序（模块依赖拓扑）与对拍验证

### 5.1 阶段拓扑（每阶段可独立验收，依赖下层）

```
L0 骨架: Spring Boot 工程 + 配置(settings 等价物) + 日志(MDC/x-request-id) + 异常映射 + 中间件链骨架 + /health /metrics
  ↓
L1 数据层: 12 表 JPA + JSONB + vector 原生 SQL + password_resets 补建 + Redis 客户端 + 缓存组件(poi/llm/tool/research_bundle)
  ↓
L2 REST 非 AI: 认证(7) 会话(4) 历史(4) 知识库(6) 反馈(10) 统计(3) 管理(3) 通勤(4) + 限流/幂等/并发/预算守卫 + 契约测试
  ↓
L3 SSE 基建: SseWriter + StreamStore + 断点续传 + 事件协议测试（先用 mock LLM 事件流打通 12 类事件 + 心跳 + 终止序列）
  ↓
L4 LLM Gateway: LlmClient(spike 结论) + ProviderRouter/Health + TokenTracking/Budget + llm_cache
  ↓
L5 工具层: 10 业务工具 + 高德 MCP + 美团 + 韧性(熔断/重试/降级) + tool_cache/poi_cache 接入
  ↓
L6 Agent 编排: Orchestrator/Research/Planner/Review + ChatAgent + AgentEngine + Skills + patch_engine + TraceRecorder
  ↓
L7 RAG: QueryRewriter + 四路召回 + 加权 RRF + credibility 重排 + Embedder/Reranker(ONNX) + 降级链
  ↓
L8 外围: TaskQueue(7 worker) + Alert + 部署编排(docker-compose) + 压测
  ↓
L9 端到端: 前端零改动联调 + eval 双回归 + 性能验收
```

依赖约束：L6 依赖 L4（LLM）与 L5（工具）；L7 依赖 L1（vector SQL）与 L4（可选 embedding 一致性）；L8 的 embedding_sync/post_chat_followup 依赖 L1/L6。**建议 L4 的 LLM spike 在 L2 并行启动**（提前锁定 R2 风险面）。

### 5.2 对拍验证方案（每阶段）

| 阶段 | 对拍手段 | 对照物 |
|---|---|---|
| L1 | `\d` schema 对比；JSONB 往返单测；同一 `SELECT ... <=>` 双端执行对比结果集；Redis key/TTL 断言（集成测试） | Python `models/*.py`、现有库实际 DDL |
| L2 | 契约测试矩阵：43 端点 × 方法/路径/参数/响应字段/错误码，双端同输入比对输出字段集；`{"detail"}` 例外清单逐条断言；bcrypt 兼容（用 Python 现有哈希登录） | `tests/` 中 controller/middleware 测试语义、trip-front/src/api 调用面 |
| L3 | SSE 协议测试：解析字节流比对事件序列（id/event/data/seq/心跳/终止序列三路径）；断点续传集成测试（X-Stream-Id+Last-Event-ID、400/403/404、只读不重放） | Python `tests/` SSE 用例同输入输出 |
| L4 | 故障注入：provider 3/5 次失败降级、60s 恢复、15s failover、usage 上报逐字段断言（含 cached） | `provider_router/` 语义 |
| L5 | 工具级单测：参数/输出/韧性（timeout/retries/熔断/fallback 文案）/缓存命中（字面+embedding≥0.85）；MCP 冒烟 + mcp-stats 指标断言 | `tests/` 工具用例、PRD §2.3 工具表 |
| L6 | mock LLM 确定性工具调用测试：四工具触发/降级（patch→modify）；Orchestrator 三阶段+重试循环；agent_steps/token_usage_logs 落库断言；followup 幂等键 | `test_agent_engine` 语义、PRD 阶段 4 验收 |
| L7 | 检索对拍：同一查询集（eval/retrieval 数据集）双端 top-N 对比；Hit@K/MRR 与 `eval-reports/baseline.json` 对比；embedding 余弦一致性（抽样 ≥0.999）；四路 vs 双路差异记录；降级链故障注入 | Python `eval/`、现有库向量 |
| L8 | 任务队列降级测试（Redis 断→内存）；告警 webhook payload 断言；/health、/health/detail 语义 | `services/alert`、`task_queue` |
| L9 | 前端切换 VITE_API_BASE 全流程回归（对照 e2e/ 6 流程）；eval fixture（**EVAL_BASE_URL 指向 Java**，驱动层保留 Python 脚本，PRD R12）；压测（登录 QPS≥6.0、SSE 流时长 15–21s 量级、并发守卫 429 行为） | `tests/e2e/`、`eval/`、`docs/performance-data/` |

**双跑工具**：一个 `dual-run` 脚本（Python 服务 vs Java 服务同输入跑同一批请求，diff 响应体/事件序列）贯穿 L2–L7，形成回归基线。

---

## 6. 风险预案

> 覆盖 PRD §5 风险表，补充实施视角的触发条件、检测手段、回退方案。

| # | 风险 | 触发信号 | 预案 |
|---|---|---|---|
| P1 | **langchain4j 工具调用格式差异**（R2，高） | spike 阶段：tool_calls delta 累积不全、usage/cached 取不到、中文 description 下发异常 | 编排层与协议层解耦（LlmClient 接口）；spike 不过的部分降级自研 OpenAI 协议层；工具 schema 用 `ToolSpecification.fromJsonSchema` 生成并逐字段对拍 Python `bind_tools` 输出 |
| P2 | **ONNX 精度漂移**（R3，高） | 余弦一致性回归 <0.999；检索 Hit@K/MRR 下降 | 首选 A 保留 B 回退（旁路 Python embedding 服务，仅 embedding 维度）；向量检索结果以配置开关隔离（四路↔双路一键回退，R13）；pre-warm 纳入启动 |
| P3 | **SSE 被中间件/框架缓冲**（R1，高） | 心跳/断线联调冒烟失败；事件延迟到达 | 手动写帧 + 每次事件 flush + GZip 对 SSE 路径跳过 + `X-Accel-Buffering: no`；协议测试解析字节流防回归 |
| P4 | **pgvector 与 ORM 冲突**（R4，高） | JPA 启动报 vector 类型未知；HNSW 查询慢/错 | 实体 `@Transient` 隔离；向量 SQL 收敛在 JdbcTemplate 单层；`ddl-auto=none` 杜绝改表 |
| P5 | **中文全文检索语义漂移**（R5，中） | 双端同一查询结果集不一致 | SQL 文本逐字复用（`'chinese'` 配置、websearch_to_tsquery、LIKE 降级顺序）；检索对拍回归覆盖 |
| P6 | **契约细节陷阱**（R6，中） | 契约测试失败：403/401 不对称、X-RateLimit-Reset 绝对时间戳、Format A/B 与 snake_case 例外、`{"detail"}` 包装 | 例外清单整理成契约测试用例表（L2 前置）；逐条断言，含头字段与 body 双重校验 |
| P7 | **断点续传与并发守卫语义**（R7，中） | 续传 400/403/404 集成测试失败；SSE 流结束信号量未释放 | StreamStore 独立组件 + 集成测试（TTL 600s、IDOR）；并发守卫自研（不依赖框架线程池）；流 finally 释放 + 断开回调兜底 |
| P8 | **多 provider failover 与 token 统计**（R9，中） | 故障注入：15s 超时未切换、usage 字段缺失 | 对照 router.py/llm.py 语义逐条故障注入测试；usage 上报结构逐字段断言（含 cached） |
| P9 | **MCP 子进程管理**（R10，中） | 冒烟失败：启动/就绪/熔断/重启时序差异 | ProcessBuilder 生命周期管理（spawn→握手探测→调用→终止→重启）；stderr 异步读防阻塞；guards 独立实现；mcp-stats 指标断言 |
| P10 | **password_resets 建表差异**（R14，中） | 现有库已存在该表但 DDL 不同 | 实施前实测；只读校验必需字段，缺失才补；`IF NOT EXISTS` 幂等；验收 1.9 对空库与现有库双跑 |
| P11 | **复刻边界争议**（R8，中） | 评审阶段对"存在但未启用"代码范围有异议 | 严格按 PRD §3 N3/N4 口径：intent.py 规则、LLM 改写、convert-to-fixture stub、不发邮件均不复刻；实施前与干系人确认并留纪要 |
| P12 | **性能不劣于基线**（R11，低） | 压测：登录 QPS<6、SSE 流时长超量级 | 虚拟线程 + 连接池调优；embedder/reranker 预热纳入启动；压测脚本复用 benchmark-http/benchmark-sse 语义 |
| P13 | **eval 体系可移植性**（R12，中） | fixture pass_rate 无法对比 | eval 驱动层保留 Python 脚本，`EVAL_BASE_URL` 指向 Java 服务（真实请求），仅业务代码 Java 化 |
| P14 | **四路召回改变检索行为**（R13，高） | 恢复四路后 top-N 与对话输出变化、指标波动 | 配置开关隔离四路/双路（一键回退）；W1/W2 权重与 w=0.3 可调；以检索评估 + 对话 eval 双回归为放行条件 |
| P15 | **任务队列语义偏差**（新增） | arq 与自研队列在退避/幂等/结果 TTL 上不一致 | key 前缀与重试退避（1/2/4s）硬编码对照；故障注入（Redis 断→内存降级）进 L8 验收 |

---

## 7. 待办与后续决策点

1. **LLM spike（L4 前置）**：锁定 langchain4j 1.x 对"流式 tool_calls + include_usage + cachedTokens"的能力边界 → 决定 LlmClient 用 langchain4j 封装还是自研协议层。
2. **ONNX 导出验证（L7 前置）**：bge-small-zh-v1.5 与 bge-reranker-base 导出、tokenizer 移植、余弦一致性回归 → 决定 A/B 方案。
3. **bcrypt 互认验证（L2 前置）**：用现有库真实密码哈希做登录单测。
4. **现有库实测**：12 表 DDL（`\d` 全量）、password_resets 现状、HNSW 索引参数、向量抽样分布（供一致性回归取样）。
5. **权重参数定稿**：四路中 spots_vec/spot_docs_vec 权重（W1/W2）与 w=0.3 先按配置项落地，检索回归后定稿。
