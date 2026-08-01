# Trip 后端 Java 重构执行计划（基于 java-migration-technical-design.md）

> **状态**：草案 v1.0
> **依据**：`docs/migration-prd-java.md`（验收标准）+ `docs/java-migration-technical-design.md`（技术方案）
> **口径**：33 个可独立验证任务，按模块依赖排序；每任务标注改动文件 / 步骤 / 验证方式 / 预估耗时 / 前置依赖 / 对应 PRD 验收条目；任务粒度 0.5~2 天
> **工程路径**：`trip-backend-java/`（新建，下文文件路径均相对该工程根）；包根 `com.trip.backend`
> **总工期**：关键路径约 38~42 人日；单人 9 周左右，2 人并行（A/B 线）约 5 周

---

## 0. 任务总览与依赖图

### 0.1 任务清单（按依赖拓扑排序）

| 阶段 | 任务 | 名称 | 预估 | 依赖 | 验收条目 |
|---|---|---|---|---|---|
| **A 工程基建** | A1 | 工程骨架 + 配置 + 日志 + 异常映射 + 健康检查 | 1d | — | 1.6, 1.8(部分) |
| | A2 | 中间件链（RequestID/Prometheus/GZip/CORS）+ 4 指标 + RateLimiter 组件 | 1d | A1 | 1.4, 1.7, 1.8, 1.5(组件) |
| | A3 | 数据层：12 表 JPA + JSONB + vector 原生 SQL + password_resets 补建 | 2d | A1 | 1.1, 1.2, 1.9 |
| | A4 | Redis 客户端 + 4 缓存组件（poi/llm/tool/research_bundle） | 1d | A3 | 1.3 |
| **B 用户/CRUD** | B1 | 认证 7 端点 + JWT + bcrypt(12) + auth 限流 | 1.5d | A2, A3 | 2.1, 1.5(auth) |
| | B2 | 会话 + 行程历史 CRUD（8 端点） | 1d | B1 | 2.2(部分) |
| | B3 | 知识库 CRUD + bulk + spot-docs（6 端点）+ knowledge 限流 | 1.5d | B1 | 2.2(部分), 2.6, 1.5(knowledge) |
| | B4 | 反馈（10 端点）+ IDOR + upsert + feedback 限流 | 1.5d | B1 | 2.2(部分), 2.3, 1.5(feedback) |
| | B5 | 统计 + 管理后台（6 端点） | 1d | B1 | 2.2(部分) |
| | B6 | 通勤 4 端点（高德 HTTP 客户端） | 2d | A2 | 2.2(部分) |
| | B7 | 幂等 + 并发守卫 + token 预算守卫（机制 + stub 路由挂载） | 1d | A2, A4 | 2.5, 1.4(幂等), 1.5(chat/recommend/global), 4.5(机制) |
| **C RAG** | C0 | TaskQueue 双后端核心（Redis 队列 + 内存降级 + 幂等键 + 退避） | 1d | A4 | 6.4(机制) |
| | C1 | Embedder + Reranker ONNX 加载 + fail-closed + 预热 + 余弦一致性 | 2d | A3 | 5.3(部分), G6 前置 |
| | C2 | 检索流水线：改写 + 双路召回 + 加权 RRF（恢复前基线） | 1.5d | A3, C1 | 5.1(双路), 5.2, 5.6(部分) |
| | C3 | 四路召回 + credibility 重排 + 降级链 + 开关 | 2d | C2 | 5.1(四路), 5.7, 5.8, 5.9 |
| | C4 | embedding_sync 任务（CRUD/bulk 触发 + 覆盖写 + 幂等） | 1d | C0, C1 | 5.4 |
| **D Agent 核心** | D1 | LLM Gateway spike + LlmClient + Provider 路由 + 15s failover | 2d | — | 6.2(部分) |
| | D2 | Token 记账三件套 + llm_cache 接入 | 1d | D1 | 4.5(部分), 4.6(部分) |
| | D3 | SSE 基建：SseWriter + StreamStore + 断点续传 | 1.5d | A4 | 3.1(帧格式), 3.3, 3.4(部分) |
| | D4 | ChatController + EventSink + 消息落库 3s flush + 标题截断 + 非旅行短路 | 1.5d | D1, D3 | 3.2, 3.5, 3.6 |
| | D5 | 工具层：10 业务工具 + 韧性 + 缓存接入 | 2d | C2, D1 | 4.3 |
| | D6 | 高德 MCP 客户端 + guards + mcp-stats 指标 | 1.5d | A4 | 6.3, 4.3(MCP) |
| | D7 | Orchestrator + Research/Planner/Review + validate_with_repair | 2d | D1, D5, D6 | 4.2 |
| | D8 | ChatAgent 双流 + AgentEngine + 四升级工具 + trip 落库 | 2d | D2, D4, D7 | 4.1, 3.7(部分) |
| | D9 | 技能系统 L1/L2/L3 + patch_engine | 1.5d | D5, D7 | 4.4, 4.1(patch) |
| | D10 | 并发守卫/预算守卫流式挂载 + TraceRecorder 落库 | 1d | B7, D8 | 4.5, 4.6 |
| | D11 | recommend 链路（recommend/recommend-stream/confirm/discard/Format A） | 1.5d | D3, D7, B7 | 2.4, 3.1(recommend-stream), 3.4(3s), 3.7(部分) |
| | D12 | post_chat_followup（压缩 + 决策 + 偏好提取 + 幂等键） | 1d | C0, D8 | 4.7 |
| **E 运维面** | E1 | 告警系统（检测/去重/调度/5 种 webhook） | 1d | A3 | 6.1 |
| | E2 | /health /health/detail 完善 + docker-compose 部署编排 | 0.5d | A1 | 6.5 |
| | E3 | 压测：登录 QPS + SSE 流时长 + 并发守卫行为 | 1d | D11, E2 | 7.3 |
| | E4 | 端到端：前端零改动联调 + eval 双回归 | 2d | D12, E1 | 7.1, 7.2 |
| | E5 | CI 流水线（全阶段测试 + 双端对拍任务） | 1d | E4 | 7.4 |

### 0.2 依赖图（简化）

```
A1 → A2 → A3 → A4 ─┬→ C0 ─┬→ C4 ─┐
     │      │      │      │      ├→ D12
     │      │      ├→ B1 → B2/B3/B4/B5
     │      │      │      └→ B6
     │      └──────┼→ B7 ─────────→ D10
     │             └→ C1 → C2 → C3 ─┬→ D5 ─→ D7 ─→ D8 ─→ D9/D10 ─→ D11 ─→ E3/E4
D1 (独立，可并行) ──→ D2 ────────────┘                    │
D1 ──→ D7/D8/D4                                    post_chat(D12)
D3 ──→ D4 ──→ D8 ──→ D11
E1/E2 依赖 A 块，可与 D 块并行；E4/E5 收口
```

**关键路径**：A1→A2→A3→C1→C2→C3→D5→D7→D8→D11→E4 ≈ 16 个任务 ≈ 24~26 人日；另一条 A1→A3→B1→B4→… 与 D1（LLM spike）可并行，缩短墙钟时间。

### 0.3 并行建议

- **线 1（数据/业务）**：A1→A2→A3→A4→B1→B2/B3/B4/B5/B6/B7→C0→C1→C2→C3→C4
- **线 2（LLM/Agent）**：D1（spike）→D2→D3→D4→D5→D6→D7→D8→D9→D10→D11→D12
- **线 3（运维）**：E1/E2 可在线 1 完成 A3 后随时启动；E3/E4/E5 收口。

---

## 1. 阶段 A：工程基建（对应 Tech Spec L0–L1）

### A1 工程骨架 + 配置 + 日志 + 异常映射 + 健康检查（1d）

**目标**：可构建可启动的 Spring Boot 工程；异常映射与响应格式（Format A/B、`{"detail"}` 例外）与 Python 一致；/health、/health/detail、/metrics 端点存在。

**改动文件**：
- `pom.xml`（Spring Boot 3.3、Java 21、web/security/data-jpa/data-redis/validation/micrometer/prometheus/jjwt/jbcrypt/langchain4j 依赖骨架）
- `src/main/resources/application.yml`（datasource、redis、jwt、限流/并发/预算/缓存/告警全部配置项，映射 settings.py 键）
- `src/main/java/com/trip/backend/Application.java`
- `config/AppConfig.java`（单例 Bean 装配）
- `web/handler/GlobalExceptionHandler.java`（AppException → Format A/B；IntegrityError → 409/400；SQLException → 500 dev/prod 区分；兜底 500）
- `web/handler/FormatResolver.java`（`/api/trip/recommend` 前缀 → Format A）
- `infra/security/JwtUtil.java`（HS256、7 天、payload `{userId,username,roleId,exp}`）
- `web/controller/HealthController.java`（/health PlainText "OK"、/health/detail JSON、/metrics）
- `utils/AppException.java`（NotFound/Unauthorized/Forbidden/BadRequest/Conflict 语义）

**步骤**：
1. 初始化 Maven 工程与配置项（对照 `config/settings.py` 全量迁移键名）。
2. 实现异常层级与 GlobalExceptionHandler，逐条对照 `exception_handlers.py`：AppException → Format A/B；IntegrityError 三类（Duplicate→409 DUPLICATE_ENTRY / FK→400 FOREIGN_KEY_VIOLATION / 其他→400 INTEGRITY_ERROR）；JWT 失效→401；SQLAlchemyError→500（dev 泄漏 / prod 隐藏）；兜底 500。
3. 实现 /health（PlainText）、/health/detail（status/timestamp/pid/uptime/memory.rss/checks 结构）、/metrics。
4. 日志：Logback + MDC（request_id 占位，A2 接入）。

**验证**：
- `./mvnw -q compile && ./mvnw spring-boot:run` 启动成功，`curl /health` 返回 `OK`。
- 异常映射参数化单测（`GlobalExceptionHandlerTest`）：逐条断言 400/401/403/404/409/500 的状态码与响应体；Format A/B 路径判定；`{"detail":...}` 例外清单（auth/限流/守卫抛出的 HTTPException 形态——A2/B7 补全）。
- **验收**：1.6（异常映射全表）、1.8（x-request-id 框架就绪，A2 补透传断言）。

### A2 中间件链 + 4 指标 + RateLimiter 组件（1d）

**目标**：中间件执行顺序与 Python 一致（Prometheus→RequestID→Idempotency→GlobalRateLimit→CORS→GZip→路由），SSE 不被缓冲；Prometheus 4 类指标；固定窗口限流器组件（6 实例配置）。

**改动文件**：
- `web/filter/RequestIdFilter.java`（透传/生成 x-request-id，响应头回写，MDC 绑定/清理）
- `web/filter/PrometheusFilter.java`（http_requests_total / http_request_duration_seconds buckets 0.005–10s / chat_request_duration_seconds 0.1–60s / tool_invocations_total；排除 /metrics 与 /health 精确路径）
- `web/filter/GzipFilter.java`（minimum_size=1024；**SSE 响应跳过压缩**）
- `web/config/CorsConfig.java`（allow_origins 白名单 + headers 含 X-Stream-Id/Last-Event-ID/x-request-id）
- `infra/ratelimit/RateLimiter.java`（固定窗口：Redis INCR+EXPIRE 降级内存；返回 count/resetAt）
- `infra/ratelimit/RateLimitRegistry.java`（6 实例：global 2000/60s、auth 10/900s、chat 200/60s、recommend 50/60s、feedback 30/3600s、knowledge 100/60s）
- `web/filter/GlobalRateLimitFilter.java`（仅 /api 前缀；响应头 X-RateLimit-Limit/Remaining/Reset 绝对时间戳）
- `web/config/FilterOrderConfig.java`（显式顺序）

**步骤**：
1. 按 main.py 注册顺序实现 5 个 Filter + CORS；RequestID 用原生 Servlet 包装（不读 body），Prometheus 用包装 Response 记录 status。
2. RateLimiter 组件：`increment(key, window)` → (count, resetAt)，Redis `INCR`+`EXPIRE ceil(window)`，异常降级内存；`X-RateLimit-Reset` 输出 `Math.ceil(resetAt)` 绝对时间戳。
3. 指标：Micrometer Counter/Histogram 名称与 label（method/path/status）对齐；`/metrics` 由 actuator prometheus 暴露。

**验证**：
- 集成测试 `MiddlewareChainTest`：断言过滤顺序（日志顺序）、SSE 端点响应未被 GZip 压缩、幂等仅作用于 recommend（B7 后完整断言）。
- `RateLimiterTest` 参数化：6 实例阈值/窗口/剩余数/Reset 头格式（绝对时间戳）。
- 抓取 `/metrics` 断言 4 类指标存在且 label 正确。
- `RequestIdFilterTest`：客户端带/不带 x-request-id 两种透传 + 日志 MDC 贯穿断言。
- **验收**：1.4（中间件顺序与不缓冲）、1.7（指标）、1.8（x-request-id 全链路）、1.5（限流器组件）。

### A3 数据层：12 表 JPA + JSONB + vector 原生 SQL + password_resets 补建（2d）

**目标**：直连现有 PG，12 表可读写；JSONB 往返一致；向量检索走原生 SQL；password_resets 幂等补建。

**改动文件**：
- `domain/entity/`：Role、User、PasswordReset、Trip、Conversation、Message、Spot、SpotDoc、Feedback、AgentStep、TokenUsageLog（11 个实体；embedding 列 `@Transient`；JSONB 列 `@JdbcTypeCode(SqlTypes.JSON)`；无 updated_at 的实体不映射该列）
- `domain/repository/`：11 个 JpaRepository（含 `@Query` 分页/级联/upsert 语义）
- `infra/db/VectorSearchRepository.java`（`1 - (embedding <=> CAST(:vec AS vector))`，city/category 过滤，`embedding IS NOT NULL`）
- `infra/db/FulltextSearchRepository.java`（`to_tsvector('chinese', ...) @@ websearch_to_tsquery('chinese', :q)` + LIKE 降级）
- `infra/db/SchemaValidator.java`（启动校验 12 表；缺失表幂等 DDL 补建，仅 password_resets 预期缺失）
- `config/DatabaseConfig.java`（HikariCP 池 10/溢出 20；`ddl-auto=none`；慢查询日志阈值 100ms）

**步骤**：
1. 对现有库执行 `\d` 全量导出，逐表编写实体（列名/类型/约束/索引/ondelete 与 models/*.py 一致）。
2. 实现 vector/全文 Repository：SQL 文本与 Python 逐字一致（`CAST(:vec AS vector)`，不得用 `::vector`）。
3. SchemaValidator：启动时 `information_schema.tables` 校验；缺 password_resets 则 `CREATE TABLE IF NOT EXISTS`（email、token unique、expires_at、used、created_at）。
4. JSONB 实体接 Jackson（**不开启** ESCAPE_NON_ASCII）。

**验证**：
- 启动连接现有库：`\d` 对比（11 表无改动、无新表）；`SELECT 1-(embedding<=>CAST(:v AS vector)) ...` 与 Python 同查询结果集一致（集成测试）。
- `JsonbRoundTripTest`：preferences/metadata/content/tags 四列往返序列化断言（嵌套中文/空数组/null）。
- `SchemaValidatorTest`：空库自动补建 + 现有库幂等 no-op（前后行数不变）。
- **验收**：1.1、1.2、1.9。

### A4 Redis 客户端 + 4 缓存组件（1d）

**目标**：Redis key 格式/TTL 与 Python 一致；4 类缓存 Redis 优先内存降级。

**改动文件**：
- `infra/redis/RedisConfig.java`（Lettuce；`isAvailable()` 探测）
- `infra/cache/PoiCache.java`（key `poi:{city}:{category}:{queryHash}`，TTL 3600s，query 归一化后 hash）
- `infra/cache/LlmCache.java`（key `llm_cache:{sha256(prompt)[:32]}`，TTL 600s，max 200）
- `infra/cache/ToolCache.java`（key `tool_cache:{tool}:{literalKey}` / embedding 模式 `embed:{text}`；索引 `tool_cache_idx:{tool}`；TTL per-tool 300–3600s；embedding 相似度命中 ≥0.85）
- `infra/cache/ResearchBundleCache.java`（key `research_bundle:{city}:{budget_tier}:{days}d:{dep}:{interestsHash}`，TTL 300s，内存 max 200，预算档位 <1000/<3000/<8000/luxury）
- `infra/cache/CacheBackend.java`（Redis/内存双后端抽象）

**步骤**：
1. 实现双后端抽象：Redis 不可用或异常 → 内存后端（与 Python `is_redis_available()` 分支一致）。
2. ToolCache 字面 key 归一化：sorted keys、字符串 trim+lower、city 字段特判、跳过 null。
3. ToolCache embedding 路径：查询向量与缓存条目向量点积（L2 归一化前提）≥0.85 命中；embedding 失败降级字面查找。

**验证**：
- `CacheKeyTest`：断言 4 类缓存 key 与 Python 实测（同一输入）完全一致。
- `CacheTtlTest`：TTL 值断言（300/600/1800/3600）；Redis 断开 → 内存降级仍可用。
- **验收**：1.3。

---

## 2. 阶段 B：用户/CRUD（对应 Tech Spec L2）

### B1 认证 7 端点 + JWT + bcrypt(12) + auth 限流（1.5d）

**目标**：register/login/info(Get/Put)/password/forgot/reset 全契约兼容。

**改动文件**：
- `web/controller/UserController.java`（7 端点；公开×3 + JWT×3；auth 限流挂载）
- `service/UserService.java`（注册查重/登录用户名或邮箱/改密验旧密/忘记密码恒成功防枚举/重置令牌 uuid4 明文入库 30min used 标志；不发送邮件仅日志）
- `domain/repository/UserRepository.java`、`PasswordResetRepository.java`
- `infra/security/PasswordHasher.java`（jBCrypt rounds=12）
- `infra/security/JwtAuthFilter.java`（HTTPBearer 语义：**缺头 403 "Not authenticated" / 坏或过期 401**；只强校验 userId+exp；授权以 DB role_id 为准）

**步骤**：
1. JwtAuthFilter 复刻不对称语义（缺 Authorization 头 → 403；token 无效 → 401）；admin 校验 `role_id==1` → 403。
2. bcrypt：`BCrypt.gensalt(12)`；用现有库真实密码哈希做互认测试。
3. forgot-password：恒返回成功（防枚举）；reset 令牌 uuid4 明文入库、expires_at=now+30min、used 标志。

**验证**：
- `AuthContractTest`：7 端点方法/路径/参数/响应字段/错误码逐条断言（对照 Python 测试语义）。
- 登录兼容：用 Python 库中既有用户密码登录成功（bcrypt rounds=12 互认）。
- 缺头 403 / 坏 token 401 / 过期 401 三条路径；admin 403。
- auth 限流：10 次/900s 第 11 次 429 + X-RateLimit-* 头断言。
- **验收**：2.1、1.5(auth)。

### B2 会话 + 行程历史 CRUD（8 端点）（1d）

**目标**：conversations 4 端点 + history 4 端点契约兼容。

**改动文件**：
- `web/controller/ConversationController.java`（GET 分页 / GET{id} / POST / DELETE）
- `web/controller/HistoryController.java`（GET trips 分页 / GET{id} / GET{id}/versions / DELETE）
- `service/ConversationService.java`、`service/HistoryService.java`
- `domain/repository/ConversationRepository.java`、`TripRepository.java`
- `web/dto/`（ConversationDetailDto 含消息 **snake_case 字段**；TripDto）

**步骤**：
1. 会话列表 `{items,total,page,pageSize}`；详情含消息（snake_case）；删除级联 messages 与 agent_steps（DB ondelete CASCADE）。
2. 历史：content 为完整行程 JSON；versions 返回 parent_trip_id 版本链（V1/V2 语义）；Trip 无 updated_at。
3. 创建默认标题；分页参数与 Python 一致。

**验证**：
- `ConversationContractTest` / `HistoryContractTest`：契约字段断言（含 snake_case 例外、级联删除后子表行数）。
- **验收**：2.2(部分)。

### B3 知识库 CRUD + bulk + spot-docs + knowledge 限流（1.5d）

**目标**：spots CRUD/分页/筛选/bulk/spot-docs 契约兼容。

**改动文件**：
- `web/controller/KnowledgeController.java`（6 端点；公开×3 + Admin×3；knowledge 限流 100/min）
- `service/KnowledgeService.java`（分页/城市/分类筛选；bulk 返回 success/failed 计数；spot-docs 带 `chroma:{available, spotDocsCount}` 状态字段）
- `domain/repository/SpotRepository.java`、`SpotDocRepository.java`
- `web/dto/`（**snake_case 响应**：GET 详情与 POST/PUT）

**步骤**：
1. spots CRUD：GET 详情与 POST/PUT 响应为 snake_case；bulk 请求体为**裸 JSON 数组**。
2. spot-docs 列表：city/source_type 过滤 + chroma 状态字段（与 Python 当前实现一致的字段结构）。
3. create/update/bulk 后触发 embedding 同步（C4 任务队列；本任务先留调用点 + stub）。

**验证**：
- `KnowledgeContractTest`：分页/筛选/裸数组 bulk/chroma 字段/snake_case 断言；Admin 403 断言。
- knowledge 限流 100/min 第 101 次 429。
- **验收**：2.2(部分)、2.6、1.5(knowledge)。

### B4 反馈（10 端点）+ IDOR + upsert + feedback 限流（1.5d）

**目标**：反馈评分/列表/统计/管理端点契约 + 权限语义。

**改动文件**：
- `web/controller/FeedbackController.java`（GET/POST /feedback、GET /feedback/message/{id} 公开、GET /feedback/stats、GET /feedback/list/{id}、admin 3 端点）
- `service/FeedbackService.java`（评分 1/-1、评论截断 500 字、tags≤10、**(user,message) 唯一 upsert**、IDOR 校验：消息归属 + 仅 assistant 消息可评分）
- `domain/repository/FeedbackRepository.java`（唯一约束 uq_feedback_user_message 冲突 → upsert 语义）
- `web/dto/`（AdminHighTokenLowSatisfaction / DailyStats / TestAlert / ConvertToFixture——convert 为 stub 恒返回 "Not implemented yet"，PRD N4）

**步骤**：
1. upsert：`INSERT ... ON CONFLICT (user_id, message_id) DO UPDATE`（对齐 Python 唯一约束 + 更新语义）。
2. IDOR：评分前校验 message 归属当前用户且 role==assistant，否则 403/400（对照 Python 语义）。
3. admin 端点：high-token-low-satisfaction、daily-stats、test-alert（触发告警 webhook，E1 完善）。

**验证**：
- `FeedbackContractTest` + `FeedbackIdorTest`（他人消息评分 403、非 assistant 400、重复评分 upsert 不重复）。
- feedback 限流 30/h 断言。
- **验收**：2.2(部分)、2.3、1.5(feedback)。

### B5 统计 + 管理后台（6 端点）（1d）

**目标**：token-usage 3 端点 + admin 3 端点契约。

**改动文件**：
- `web/controller/StatsController.java`（summary/stats/logs；scope=global 需 role_id==1）
- `web/controller/AdminController.java`（agent-trace by message_id / by conversation_id+limit / mcp-stats）
- `service/StatsService.java`（`{window:{current,limit,resetAt(ms)}, totalSinceStart}`；logs 含 cachedTokens、latencyMs）
- `service/AdminService.java`（agent_steps 明细/摘要；mcp-stats 快照字段 calls/successes/failures/cacheHits/circuitOpenCount/avgDurationMs——D6 后填真实值）
- `domain/repository/TokenUsageLogRepository.java`、`AgentStepRepository.java`

**步骤**：
1. token-usage summary/stats 的 window 计算（current/limit/resetAt 毫秒时间戳）；logs 分页明细。
2. agent-trace：单 message_id 明细（steps 有序）+ conversation_id 摘要（limit 分页）。
3. mcp-stats：先返回全 0 快照，D6 接入真实指标。

**验证**：
- `StatsContractTest` / `AdminContractTest`：字段/分页/role_id==1 权限断言。
- **验收**：2.2(部分)。

### B6 通勤 4 端点（高德 HTTP 客户端）（2d）

**目标**：geocode/inputtips/nearby/optimal 契约（裸对象/`{code:0,...}` 例外格式）+ 高德 API 调用。

**改动文件**：
- `web/controller/CommuteController.java`（4 端点，公开）
- `service/CommuteService.java`（多目的地多方式择优：driving/walking/transit/cycling、compare_modes、polyline、has_subway、per_mode）
- `service/GeocodeService.java`（高德 REST：地理编码/联想/周边 POI）
- `infra/http/AmapHttpClient.java`（rest 客户端 + 重试：429 Retry-After 封顶 30s）
- `web/dto/CommuteDtos.java`

**步骤**：
1. geocode/inputtips/nearby 返回**裸对象**（无 Format 包装）；optimal 返回 `{code:0, data, message:"ok"}`。
2. optimal：多目的地并行计算、多方式择优、compare_modes 对比、polyline/has_subway/per_mode 字段透传。
3. 高德 key 缺失/失败 → 按 Python fallback 语义返回（对照 commute_service.py）。

**验证**：
- `CommuteContractTest`：4 端点格式例外断言（裸对象、code:0 包装）+ 高德 mock 响应字段透传。
- **验收**：2.2(部分)。

### B7 幂等 + 并发守卫 + token 预算守卫（机制 + stub 挂载）（1d）

**目标**：三个守卫组件语义复刻，路由挂载点就绪。

**改动文件**：
- `web/filter/IdempotencyFilter.java`（仅 POST + `/api/trip/recommend` 前缀；key=`{userId或anonymous}:{idempotency-key}`；进程内存 TTL 3600s；只缓存 2xx JSON 响应）
- `infra/guard/ConcurrencyGuard.java`（全局 Semaphore(10) + per-user Semaphore(1)，非阻塞 tryAcquire，返回 release 回调）
- `infra/guard/TokenBudgetManager.java`（用户 50K/h → 429、全局 200K/min → 503；固定窗口惰性重置）
- `web/filter/GuardFilter.java`（chat/recommend 路由挂载：concurrency + token 预算；SSE 端点把 release 存入 request attribute 由流 finally 释放）
- `web/controller/StubTripController.java`（recommend/chat 最小 stub 路由，供守卫集成测试；D4/D11 替换）

**步骤**：
1. 幂等：命中返回缓存体（原响应头丢失——保持 Python 行为）；2xx 才缓存、非 JSON 不缓存。
2. 并发守卫：`tryAcquire(userId)` 双信号量非阻塞；429 `{"code":429,"error":"系统繁忙，请稍后再试"}`。
3. Token 预算：入口 check → 429/503；record 回写（D2 接入 LLM 记账后闭环）。

**验证**：
- `IdempotencyTest`：同 key 二次请求返回缓存 JSON、TTL、仅 recommend 路径生效、SSE 路径不生效。
- `ConcurrencyGuardTest`：全局 10/单用户 1 超限 429；release 幂等。
- `TokenBudgetTest`：用户超限 429 / 全局超限 503；窗口重置。
- **验收**：2.5、1.4(幂等)、1.5(chat/recommend/global)、4.5(机制部分)。

---

## 3. 阶段 C：RAG（对应 Tech Spec L7 + 模型加载；C0 为任务队列前置）

### C0 TaskQueue 双后端核心（1d）

**目标**：arq 语义的任务队列组件（Redis List + 内存降级），供 C4/D12 使用。

**改动文件**：
- `infra/task/TaskQueue.java`（enqueue(func, args, jobId)：Redis 可用 → LPUSH `arq:queue:{name}` + 结果 `arq:result:{jobId}` SETEX 3600s；否则内存 @Async 降级）
- `infra/task/WorkerScheduler.java`（@Scheduled 消费：BRPOP → 执行 → 失败重试 `max_tries=3` 退避 1/2/4s → job_timeout 300s 超时）
- `infra/task/TaskRegistry.java`（worker 函数注册表：embedding_sync×2、post_chat_followup、fetch_city_wiki、demo×3）
- `infra/task/DegradedTaskRunner.java`（内存降级 fake_ctx 等价物）

**步骤**：
1. job_id 幂等：`SETNX`（或等价键）防重复入队；相同 job_id 只执行一次。
2. 重试与退避：失败按 attempt 退避 1/2/4s；重试耗尽标记死信。
3. 降级：Redis 不可用 → 同签名内存执行（fake_ctx: job_id/job_try/degraded 占位）。

**验证**：
- `TaskQueueTest`：幂等键、max_tries=3 退避时序、job_timeout、结果 TTL 3600s、Redis 断开降级内存仍执行。
- **验收**：6.4(机制部分)。

### C1 Embedder + Reranker ONNX 加载 + fail-closed + 预热 + 余弦一致性（2d）

**目标**：Java 侧产出与现有库向量语义一致的 embedding；reranker 可用；fail-closed + 预热语义保留。

**改动文件**：
- `infra/ai/OnnxModelLoader.java`（onnxruntime 加载/会话管理）
- `infra/ai/BgeEmbedder.java`（bge-small-zh-v1.5 ONNX + WordPiece tokenizer；查询前缀"为这个句子生成表示以用于检索相关文章："；**L2 normalize**；batch=32；40s 超时）
- `infra/ai/BgeReranker.java`（bge-reranker-base CrossEncoder + sigmoid 归一化）
- `infra/ai/EmbedderHealth.java`（fail-closed：启动 `markUnavailable()`，后台 `warmup()` 成功才恢复）
- `web/controller/EmbedDebugController.java`（**仅 dev profile** 暴露 `POST /dev/embed`，供一致性对拍脚本调用；生产不注册）
- `scripts/export_onnx/export_bge.py`（transformers.onnx 导出脚本，实施用）
- `scripts/cosine_consistency.py`（抽样现有库向量 vs Java `/dev/embed` 复算，余弦一致性对拍脚本）

**步骤**：
1. 导出 bge-small-zh-v1.5 与 bge-reranker-base 为 ONNX（float32），tokenizer 移植（WordPiece 或 tokenizer.json 解析）。
2. 实现 Embedder/Reranker；fail-closed + 预热（AgentEngine 启动时 `warmup()`，失败保持降级不阻塞）。
3. 余弦一致性回归：抽样 50 条现有 `spots.embedding`，Java 复算同文本向量，余弦 ≥0.999 放行。

**验证**：
- `python scripts/cosine_consistency.py --java http://localhost:8080/embed`（对拍脚本）：50 条抽样 ≥0.999。
- `EmbedderHealthTest`：fail-closed（未预热时调用抛错/降级）→ 预热成功恢复；预热失败保持降级。
- `RerankerDegradeTest`：模型不可用 → 返回原始顺序（分数 0）。
- **验收**：5.3(部分)、G6 前置（Hit@K/MRR 放行前提）。

### C2 检索流水线：改写 + 双路召回 + 加权 RRF（恢复前基线）（1.5d）

**目标**：复刻当前生效双路检索（rating + pg_fulltext），结果与 Python 对拍一致。

**改动文件**：
- `service/rag/QueryRewriter.java`（清洗去标点 → extractKeywords（中英停用词表 + len>=2 + 去重）→ city 前缀拼装）
- `service/rag/RatingSearch.java`（`ORDER BY rating DESC NULLS LAST`，_source=rating）
- `service/rag/FulltextSearch.java`（websearch_to_tsquery SQL + LIKE 降级）
- `service/rag/Rrf.java`（rrf_merge / rrf_merge_with_weights：`weight/(k+rank)`，k=60，score_adjuster=(0.5+cred)）
- `service/rag/RetrievalPipeline.java`（编排：改写 → 双路 → 加权 RRF（0.7/0.5）→ 截断 limit=5）

**步骤**：
1. SQL 逐字复用 Python（`'chinese'` 配置、coalesce、NULLS LAST）。
2. 加权 RRF：pg_fulltext=0.7 / rating=0.5，credibility 乘数接入（spot_docs 才有 cred；spots 用 0.5）。
3. 失败降级链：全文失败 → LIKE；RRF 加权失败 → 普通 RRF。

**验证**：
- 检索对拍：`python eval/retrieval/run.py --base-url http://localhost:8080`（EVAL_BASE_URL 指向 Java）同一查询集，双端 top-5 对比；Hit@K/MRR 对照 `eval-reports/baseline.json`。
- `RetrievalPipelineTest`：降级链逐级触发（全文失败→LIKE；embedding 不可用→跳向量路）。
- **验收**：5.1(双路)、5.2、5.6(部分)。

### C3 四路召回 + credibility 重排 + 降级链 + 开关（2d）

**目标**：恢复被注释的两条向量召回 + rerank（设计意图补全 G9），且可一键回退双路。

**改动文件**：
- `service/rag/VectorSearchSpots.java`（`1-(embedding<=>CAST(:vec AS vector))`，embedding IS NOT NULL，city/category 过滤）
- `service/rag/VectorSearchSpotDocs.java`（JOIN spots 按 city 过滤；向量失败降级全文再聚合）
- `service/rag/CredibilityService.java`（authority/freshness/agreement/citation/evidence 5 维 + 综合分；freshness 30/365 天线性衰减；AUTHORITY_DEFAULTS 表）
- `service/rag/RerankWithCredibility.java`（rerank sigmoid → `final=(1-w)*rerank + w*cred`，w=0.3；模型不可用降级 RRF 顺序）
- `config/rag.properties`（开关 `rag.four-way.enabled`、权重 W1/W2、w=0.3、limit=5）

**步骤**：
1. 两路向量召回 + 接入加权 RRF（新权重 W1/W2 配置项，默认值以检索回归定稿）。
2. credibility 重排接入最终排序；不可用降级原始顺序。
3. 配置开关隔离四路/双路（一键回退，R13）。

**验证**：
- 指标/日志断言四路调用次数（`tool_invocations` 或计数日志）；双路 vs 四路 top-N 结果集差异记录。
- `RetrievalEvalTest`：Hit@K / MRR ≥ Python 双路基线，且 ≥ 恢复前实测（C2 基线）。
- 故障注入：embedding 不可用 → 自动回双路；rerank 不可用 → 原始顺序；检索始终可用。
- **验收**：5.1(四路)、5.7、5.8、5.9。

### C4 embedding_sync 任务（1d）

**目标**：spots create/update/bulk 后异步算 embedding 覆盖写（幂等）。

**改动文件**：
- `task/EmbeddingSyncTask.java`（worker：按 spot_id 取 name+description → BgeEmbedder → `UPDATE spots SET embedding=CAST(:vec AS vector) WHERE id=:id`；失败入队重试，job_id=`embedding_sync:{spot_id}`）
- `service/KnowledgeService.java` 改造：create/update/bulk 成功处调用 `taskQueue.enqueue(embeddingSync, spotId, jobId=...)`
- `config/rag.properties`：`rag.embedding-sync.enabled`

**步骤**：
1. worker 注册到 C0 TaskRegistry（job_id 幂等键 `embedding_sync:{spot_id}`）。
2. CRUD/bulk 触发点接入；覆盖写（重复任务以最新为准）。
3. embedding 不可用时任务失败退避重试（max_tries=3）。

**验证**：
- `EmbeddingSyncTaskTest`：CRUD/bulk 后落库断言 embedding 非空且余弦≈1（同文本重算）；重复入队只执行一次（幂等）。
- **验收**：5.4。

---

## 4. 阶段 D：Agent 核心（对应 Tech Spec L3–L6）

### D1 LLM Gateway spike + LlmClient + Provider 路由 + 15s failover（2d）

**目标**：锁定 langchain4j 能力边界（Tech Spec 决策点 1），产出 LlmClient 并复刻 provider 路由/健康/failover。

**改动文件**：
- `infra/llm/LlmClient.java`（接口：stream(messages, tools, sink) / invoke）
- `infra/llm/OpenAiLlmClient.java`（langchain4j `OpenAiStreamingChatModel` 封装；spike 未覆盖处降级自研协议层）
- `infra/llm/ProviderRegistry.java`（deepseek/kimi/agnese：base_url/model/api_key，映射 settings）
- `infra/llm/ProviderHealthRegistry.java`（HEALTHY/DEGRADED/DOWN：连续失败 3/5、60s 自动恢复窗口、recordSuccess 回 HEALTHY）
- `infra/llm/ScenarioRouter.java`（PLANNING=[deepseek,kimi,agnese]、CHAT=[agnese,kimi,deepseek]、RESEARCH=[agnese,deepseek,kimi]）
- `infra/llm/LLMContext.java`（ThreadLocal userId/endpoint，等价 token_tracker.LLMContext）
- `docs/llm-spike-notes.md`（spike 结论记录）

**步骤**：
1. **Spike（0.5~1d）**：对三 provider 发流式工具调用请求，验证 (a) 流式中 tool_calls 增量累积；(b) 末帧 usage（含 cachedTokens）；(c) 中文工具 description 下发。结论写 spike 文档，决定 LlmClient 实现路径（langchain4j 封装 or 自研协议层）。
2. Provider 健康状态机 + 场景优先级路由 + `callWithFallback(scenario, fn, fallbackFn, 15s)`（超时记失败 → 切 fallback；fallback 无超时保护——对齐 Python）。
3. 流式超时 60s（ChatAgent）、非流式超时按工具配置。

**验证**：
- `ProviderFailoverTest`：主 provider 15s 超时 → 切 fallback 成功；连续 3/5 次失败降级；60s 后自动恢复探测。
- `LlmStreamTest`：mock OpenAI 响应断言 chunk 回调、tool_calls 累积、usage 提取。
- **验收**：6.2(部分)。

### D2 Token 记账三件套 + llm_cache 接入（1d）

**目标**：on_llm_end 记账、环形缓冲告警、落库、预算回写、llm_cache。

**改动文件**：
- `infra/llm/TokenTrackingCallback.java`（LLM 调用后提取 usage：prompt/completion/cached 兼容 `promptCacheHitTokens` 等命名；`prompt+completion<=0` 跳过；异步落库）
- `infra/llm/TokenMonitor.java`（环形缓冲 1000、单次 >100K 告警、落库 token_usage_logs 字段全）
- `infra/llm/TokenBudgetManager.java` 接入（recordUserUsage/recordGlobalUsage 回写，与 B7 守卫闭环）
- `infra/llm/LlmCache.java` 接入（命中返回、TTL 600s）

**步骤**：
1. TokenTrackingCallback 挂到 LlmClient 每次调用（fire-and-forget 记账）。
2. TokenMonitor：环形缓冲 + 告警阈值 + DB 写入（user_id/request_type/route/conversation_id/message_id/四 token 字段/latency_ms）。
3. llm_cache：prompt 哈希命中直接返回（仅非流式调用场景，对齐 Python 使用面）。

**验证**：
- `TokenTrackingTest`：usage 逐字段断言（含 cached）；`total>100K` 告警日志；落库行字段完整。
- 预算闭环：真实 LLM 调用后 check_user_budget 数值增长；超限 429/503。
- **验收**：4.5(部分)、4.6(token 部分)。

### D3 SSE 基建：SseWriter + StreamStore + 断点续传（1.5d）

**目标**：帧格式精确、StreamStore 三 key 结构、续传 400/403/404、只读重放。

**改动文件**：
- `web/sse/SseWriter.java`（帧格式 `id: {seq}\nevent: {type}\ndata: {json}\n\n`；无 id 帧（stream_meta/end）、无 type 帧（end）；每事件 flush；`X-Accel-Buffering: no`；心跳调度）
- `web/sse/StreamStore.java`（createStream/appendEvent/getEventsSince/getStreamState/markComplete/deleteStream；Redis HASH+LIST+STRING；TTL 600s append 续期；单事件 ≤64KB；内存降级）
- `web/sse/ResumeHandler.java`（X-Stream-Id + Last-Event-ID 同时存在才触发；重发 seq>lastSeq 保留原 id 并追加 end；错误映射 400/404/403）
- `web/sse/SseEvent.java`（seq/type/data/createdAt）

**步骤**：
1. SseWriter 线程安全帧队列 + 虚拟线程消费 + flush；断开回调（供守卫释放/StreamStore 收尾）。
2. StreamStore 按 stream_store.py 逐方法复刻（含 seq 原子自增、events LRANGE、lastSeq>totalSeq 抛错语义）。
3. 心跳：空闲 15s（chat）/ 3s（recommend-stream）由 D4/D11 配置。

**验证**：
- `SseProtocolTest`：字节流解析断言帧格式/seq 自增/终止序列（complete→end、error→end、仅 error）三路径。
- `StreamStoreResumeTest`：续传重放（原 id 保留、追加 end、只读不改状态）；400（非法/超界）/404（不存在/过期）/403（owner 不匹配）；TTL 600s。
- **验收**：3.1(帧格式)、3.3、3.4(部分)。

### D4 ChatController + EventSink + 消息落库 3s flush + 标题 + 非旅行短路（1.5d）

**目标**：chat SSE 端点骨架：12 类事件分发、assistant 消息增量落库、标题截断、非旅行短路（mock LLM 阶段）。

**改动文件**：
- `web/controller/ChatController.java`（POST /api/trip/chat；SSE 头四件套；X-Stream-Id/Last-Event-ID 传入 ResumeHandler；chat 限流 200/min + 守卫挂载）
- `service/chat/EventSink.java`（onEvent 接口：SSE 写 + StreamStore 双写 + 心跳检测）
- `service/chat/MessagePersistenceService.java`（user 消息立即落库；assistant 先建空行取 id → 每 3s 增量 flush → complete/error 强制 flush 附 `metadata.usage`；标题取首条消息前 20 字符 + "..." 仅当空/"新对话"）
- `service/chat/NonTravelShortCircuit.java`（非旅行问题：chunk → complete usage 全 0 → end，不发工具）

**步骤**：
1. EventSink 双写：每个业务事件写 SSE + appendEvent 持久化；stream_meta（`stream:{uuid}`）为首事件（Redis 可用时）。
2. 落库管线：3s 定时 flush + 终态强制 flush；complete 事件 usage 结构（含 null 情况）。
3. 先用 mock LLM 打通全事件流（D8 换真实 ChatAgent）。

**验证**：
- `ChatSseMockTest`（mock LLM）：12 类事件名称/顺序/data 结构逐一对齐；非旅行短路（chunk→complete usage 全 0→end）。
- `MessagePersistenceTest`：3s 增量 flush 断言（中间状态行数）、complete 附 usage、标题截断 20 字符规则。
- **验收**：3.2、3.5、3.6。

### D5 工具层：10 业务工具 + 韧性 + 缓存接入（2d）

**目标**：10 业务工具参数/输出/韧性/缓存与 Python 逐一对齐。

**改动文件**：
- `service/agent/tools/RetrieveKnowledgeTool.java`（category 中文映射{景点/美食/住宿/交通}；query 关键词推断；poi_cache 读写仅 attraction/food；调用 C2/C3 检索管线；`with_resilience(timeout=8s, retries=0, fallback="知识库暂时不可用...", 熔断 5/30)`）
- `service/agent/tools/SearchHotelsTool.java`（timeout=10s/1；ttl 300s）
- `service/agent/tools/CalculateDistanceTool.java`（car 走高德路网失败回退 Haversine；timeout=5s/1；ttl 3600s）
- `service/agent/tools/CommuteTools.java`（compute_optimal_commute 20s/1 不缓存；search_commute_tips 8s/1 不缓存；search_nearby_commute_pois 8s/1 不缓存）
- `service/agent/tools/MeituanTool.java`（ProcessBuilder `npx @meituan-travel/ht-ai`，150s 超时，列表传参防注入，MEITUAN_HT_TOKEN 校验）
- `service/agent/tools/ToolSpecRegistry.java`（工具 schema：name/description/参数——与 Python bind_tools 输出对拍）
- `infra/resilience/CircuitBreaker.java`（三态机：CLOSED/OPEN/HALF_OPEN；threshold=5、recovery=30s；CLOSED 下成功不重置失败计数）
- `infra/resilience/ToolResilienceWrapper.java`（超时/重试/熔断/fallback；429 Retry-After 封顶 30s；指数退避 2^n 封顶 10s）

**步骤**：
1. 实现 CircuitBreaker 三态机 + ToolResilienceWrapper（与 resilience.py 逐行语义对照）。
2. 10 工具逐个实现并挂 `with_resilience` 参数表（上表）+ tool_cache（retrieve_knowledge/search_hotels/calculate_distance 三个配置项）。
3. 工具失败返回 fallback 文案（不抛）；熔断 OPEN 直接短路 fallback。

**验证**：
- `ToolContractTest`：10 工具参数/输出/fallback 文案逐条断言（对照 PRD §2.3 工具表）。
- `ResilienceTest`：熔断三态转换时序、429 Retry-After 优先、指数退避封顶、CLOSED 不重置失败计数。
- `ToolCacheHitTest`：字面命中 + embedding 相似度≥0.85 命中。
- **验收**：4.3。

### D6 高德 MCP 客户端 + guards + mcp-stats（1.5d）

**目标**：npx 子进程 + JSON-RPC 2.0 + guards 复刻 + 指标接入 B5。

**改动文件**：
- `service/mcp/AmapProcess.java`（ProcessBuilder spawn `npx -y @amap/amap-maps-mcp-server`；注入 AMAP_MAPS_API_KEY/AMAP_KEY；stdout/stderr 异步读防阻塞；terminate/重启）
- `service/mcp/JsonRpcClient.java`（tools/list 握手探测 10×1s 就绪；tools/call 30s 超时；id 递增；错误提取）
- `service/mcp/AmapClient.java`（callTool/listTools 门面）
- `service/mcp/Guards.java`（MCPCircuitBreaker fail_max=5/reset 60s；MCPRateLimiter 令牌桶 3/s capacity 5；MCPCache TTL 1800s 仅 maps_weather/maps_geo；MCPMetrics 快照）
- `service/mcp/ToolLoader.java`（MCP schema → 工具定义动态转换）
- `service/AdminService.java` 接入（mcp-stats 真实快照）

**步骤**：
1. 子进程生命周期：spawn → tools/list 轮询就绪 → 调用 → 熔断/限流 → 重启；退出码/启动失败错误文案与 Python 一致。
2. guards 按 Python 语义独立实现（pybreaker 语义：open 短路、half-open 试探）。
3. 指标：calls/successes/failures/cache_hits/circuit_open_count/avg_duration_ms 快照 → mcp-stats。

**验证**：
- `McpSmokeTest`：启动/就绪/调用成功（真实或 mock server 进程）。
- `McpGuardsTest`：连续 5 失败熔断、60s 半开试探成功恢复；令牌桶 3/s 超限报错；缓存命中（仅可缓存工具）。
- `McpStatsTest`：快照字段断言。
- **验收**：6.3、4.3(MCP 部分)。

### D7 Orchestrator + Research/Planner/Review + validate_with_repair（2d）

**目标**：research→plan→review 三阶段 + 重试循环 + modify 双模式（Tech Spec §3.2 全文）。

**改动文件**：
- `service/agent/Orchestrator.java`（plan/modify；MAX_REVIEW_RETRIES=2；progress 事件；usage 四键合并；_mergePartialPlan；_parseJsonSafe(repair)）
- `service/agent/ResearchAgent.java`（并行 5 工具 → ResearchBundle；tool_start/tool_end 事件 key=attractions/food/hotels/weather/distance）
- `service/agent/PlannerAgent.java`（主 LLM 失败切 fallback_llm；PlannerInput.feedback 注入）
- `service/agent/ReviewService.java`（JSON 解析/repair → 天数一致（局部模式跳过）→ 预算≤1.15× → budgetBreakdown 五键 → 候选池封闭世界 → LLM 二层审阅（前 3 天、截断 2000、warning 不强制打回））
- `service/agent/RepairJson.java`（repair_json 等价：最外层 {} 提取、markdown 代码块剥离）
- `service/agent/dto/`（PlanRequest/PlanResult/ResearchInput/ResearchBundle/PlannerInput/ReviewResult/TokenUsage——dataclass 等价 record）
- `service/agent/ResearchBundleCache.java` 接入（research_bundle:{...} 300s）

**步骤**：
1. 编排循环：`for attempt in 0..2 { review(); if passed break; planner.feedback=feedback 重跑 }`；最后一轮不重试。
2. modify：`is_partial = targetDays 非空` → 跳过 research（skipped=true 事件）→ planner 只输出修改天 → merge 回原行程（按 day 替换 + budgetBreakdown 增量重算）→ review。
3. progress 事件结构：`{type, data:{stage:research|plan|review|save, status:start|done, attempt?, duration_ms?, passed?, retry?, mode?, skipped?}}`。

**验证**：
- `OrchestratorTest`（mock LLM）：三阶段顺序与 progress 事件序列；review 失败 → feedback 注入重跑 ≤2 次；预算超 15% 打回；封闭世界校验（候选池外 spot 打回）；modify 局部/全量模式；merge 正确性（未改天保留）。
- **验收**：4.2。

### D8 ChatAgent 双流 + AgentEngine + 四升级工具 + trip 落库（2d）

**目标**：chat 前台链路（单次流式 + 流后分派）与 trip 落库/trip_planned/trip_diff。

**改动文件**：
- `service/agent/ChatAgent.java`（Tech Spec §3.3 全量：预检测/单次流式/四工具分派/卡片/降级）
- `service/agent/AgentEngine.java`（chat()/recommend()；共享 llm/tool_cache/skill_registry；embedding fail-closed + warmup 启动）
- `service/agent/TriggerTools.java`（trigger_plan/trigger_modify/trigger_patch 参数 schema + docstring 与 Python 一致）
- `service/agent/TripPersistenceService.java`（_persist_trip 语义：user_id/from_city/parsed/budget/parent_trip_id/status；trip_planned 事件；trip_diff 构建）
- `service/chat/` 对接：EventSink 接 ChatAgent onEvent；complete 事件 usage 合并

**步骤**：
1. 预检测：附近/通勤关键词直调 commute（绕过 resilience/tool_cache）→ 发 card → 结果注入 system prompt。
2. 流式：bind_tools（9+3 工具，amap 前 3 个失败静默）→ 逐 chunk 事件 → 累积 tool_calls → 流后分派四分支（trigger_plan/modify/patch/select_skill/其他卡片）；工具结果不二次回注 LLM。
3. 落库：plan 成功 → persist(completed) + trip_planned；modify/patch → persist(candidate, parent_trip_id) + trip_diff（day/period/oldSpot/newSpot，空值 "(无)"）；patch 失败降级 modify（`第X天Y更换为Z`, target_days=X）。
4. AgentEngine：user_id<=0 从 trip_meta 兜底；无有效 user_id 不落库只回 JSON；无 trip_meta modify 返回固定文案。

**验证**：
- `ChatAgentToolTest`（mock LLM 确定性 tool_calls）：四工具触发与降级；卡片事件结构（info_text≤1500/poi_list≤10/commute_compare≤5+recommended:0）；usage 合并（_merge_usage 四键）。
- `TripPersistenceTest`：trip_planned/trip_diff 事件字段 + trips 表状态流转断言。
- `AgentEngineChatTest`：完整 chat 流程（偏好加载/上下文注入/complete 事件）。
- **验收**：4.1、3.7(部分)。

### D9 技能系统 L1/L2/L3 + patch_engine（1.5d）

**目标**：技能三层披露 + 执行循环；槽位级 patch 修改。

**改动文件**：
- `service/agent/skills/SkillRegistry.java`（L1 目录 name/description/tags 常驻上下文；L2 选中才读整篇 SKILL.md；L3 执行）
- `service/agent/skills/SkillLoader.java`（读取 `.claude/skills` 目录）
- `service/agent/skills/SkillRuntime.java`（多轮 tool calling，MAX_SKILL_ITERATIONS=10）
- `service/agent/skills/SelectorTool.java`（select_skill 工具 + extract_select_skill_call 解析；关键词粗选兜底）
- `service/agent/patch/PatchEngine.java`（SUPPORTED_OPS=replace_slot/remove_slot/swap_slot；PatchError）
- `service/agent/ChatAgent.java` 改造（_run_selected_skill：注入 6 底层工具 + meituan_query_tool）

**步骤**：
1. Registry/Loader：L1 目录进 system prompt（skill_catalog_prompt 等价）；L2/L3 按选择加载。
2. SkillRuntime：LLM 借助底层工具自行编排，迭代上限 10 轮。
3. PatchEngine：applyPatch 三操作；PatchError/任意异常 → ChatAgent 降级 modify。

**验证**：
- `SkillRegistryTest`：L1 目录披露、未注册技能返回 None 继续默认文本回复、MAX_SKILL_ITERATIONS 上限。
- `PatchEngineTest`：replace/remove/swap 正例 + 非法 op/槽位 PatchError + 降级 modify 参数断言。
- **验收**：4.4、4.1(patch 部分)。

### D10 并发守卫/预算守卫流式挂载 + TraceRecorder 落库（1d）

**目标**：流式端点守卫 finally 释放 + agent_steps 轨迹落库。

**改动文件**：
- `service/agent/TraceRecorder.java`（buffer + flush 批量插入 agent_steps；失败只 warn）
- `web/filter/GuardFilter.java` 完善（SSE finally 释放：request attribute release + 断开回调兜底）
- `service/chat/ChatEventSink.java` 接入（流结束/断开 → release + markComplete + 消息强制 flush）
- `service/agent/AgentEngine.java` 接入（chat/recommend 完成/异常 → trace.add(complete/error) + flush）

**步骤**：
1. 流式端点：守卫 release 存 request attribute，流 finally 调用；客户端断开（IOException）回调兜底释放。
2. TraceRecorder：step 顺序、type（tool_start/tool_end/chunk/complete/error）、args/output/duration_ms/error 字段。

**验证**：
- `ConcurrencyStreamTest`：10 并发 chat 中第 11 个 429；流中断（客户端断开）后信号量释放（后续请求可进）。
- `TraceRecorderTest`：agent_steps 批量落库字段断言；失败降级 warn 不影响主流程。
- **验收**：4.5、4.6。

### D11 recommend 链路 + 状态机 + Format A + 幂等挂载（1.5d）

**目标**：recommend/recommend-stream/confirm/discard 全契约 + 幂等正式接入。

**改动文件**：
- `web/controller/TripController.java`（POST /trip/recommend 幂等挂载；POST /trip/recommend-stream SSE；POST /trip/{id}/confirm、/discard）
- `service/AgentEngine.java` recommend()（并行 ensureAmapTools+loadPreferences；fallback_llm；Orchestrator.plan；validate_with_repair 兜底；raise "Agent 多次输出无效 JSON"）
- `service/agent/RecommendEventSink.java`（start 事件 city/days/budget；progress research/plan/review/save；tool_start/end key 五类；心跳 3s；complete 完整结果）
- `service/TripService.java` confirm/discard（仅 status=="candidate" 流转 completed/discarded）

**步骤**：
1. recommend（非流式）：Format A `{success, data}`；幂等中间件命中返回缓存（原响应头丢失）。
2. recommend-stream：事件序列 start→progress+tool_*→heartbeat(3s)→complete/error；TTL/续传同 chat。
3. confirm/discard 状态机：candidate→completed/discarded；非 candidate 拒绝。

**验证**：
- `RecommendContractTest`：Format A；幂等同 key 缓存；confirm/discard 状态机单测（含非法流转 400/404）。
- `RecommendStreamTest`：事件序列逐帧断言（含 3s 心跳、usage 结构）。
- 前端 TripGenerating 页冒烟（切换 VITE_API_BASE）。
- **验收**：2.4、3.1(recommend-stream)、3.4(3s)、3.7(部分)。

### D12 post_chat_followup（1d）

**目标**：对话压缩 + 关键决策 + 偏好提取，幂等键一致。

**改动文件**：
- `task/PostChatFollowupTask.java`（worker：compress_conversation → 决策记录（is_planning 才做）→ 偏好提取；job_id=`post_chat:followup:{conversation_id}`）
- `service/SummaryService.java`（压缩对话摘要/recap；append_key_decision）
- `service/chat/PreferenceExtractor.java`（最近 10 条消息 content[:200] 拼接 → LLM 提取 → 增量合并 interests/avoid 去重追加、pace/budget_level/companions 覆盖）
- `web/controller/ChatController.java` 接入（流结束入队）

**步骤**：
1. worker 注册 C0 TaskRegistry；is_planning 由 API 端预计算传入。
2. 压缩失败抛错（入重试/死信）；决策失败 warn 不抛；偏好提取失败不影响主流程。
3. 增量合并逻辑照搬（list(dict.fromkeys(...))）。

**验证**：
- `PostChatFollowupTest`：幂等键（同 conversation 重复入队只执行 1 次）；compressed/decision_recorded/decision_skipped 标志；偏好合并去重断言（mock LLM 输出）。
- **验收**：4.7。

---

## 5. 阶段 E：运维面（对应 Tech Spec L8–L9）

### E1 告警系统（1d）

**目标**：300s 周期检测、满意率公式、指纹去重、5 种 webhook payload。

**改动文件**：
- `service/alert/AlertDetector.java`（窗口 60min；`rate = up/(up+down)`；条件 total≥5 且 rate<0.5；recentDownComments 最近 5 条）
- `service/alert/AlertDeduplicator.java`（`md5("{alert_type}:{key_info}")` 指纹；冷却 3600s）
- `service/alert/AlertScheduler.java`（@Scheduled 300s；`alert_enabled=false` 默认关闭）
- `service/alert/AlertWebhook.java`（feishu/slack/dingtalk/wecom/custom 5 种 payload；失败重试 3 次退避 1/3/9s；标题"⚠️ Feedback 满意率告警"）
- `web/controller/FeedbackController.java` 的 test-alert 端点接入

**步骤**：
1. 检测→去重→发送→mark_sent 循环；fingerprint 冷却语义。
2. 5 种 payload 结构逐字段复刻（feishu interactive card、slack blocks、dingtalk markdown、wecom markdown、custom 对象）。

**验证**：
- `AlertWebhookTest`：mock webhook server 断言 5 种 payload 请求体；重试退避 1/3/9s。
- `AlertSchedulerTest`：rate<0.5 且 total≥5 触发；冷却期内不重复发送。
- **验收**：6.1。

### E2 /health /health/detail 完善 + docker-compose 部署编排（0.5d）

**目标**：健康检查语义 + 三服务编排。

**改动文件**：
- `web/controller/HealthController.java` 完善（detail 含 status/timestamp/pid/uptime/memory.rss/checks；health 语义与 Python 一致）
- `infra/health/HealthProbe.java`（DB/Redis/MCP 进程存活检查接入 detail）
- `docker-compose.yml`（app/postgres+pgvector/redis 三服务；Java 镜像 + 健康检查）
- `Dockerfile`

**步骤**：
1. health/detail 结构与 Python `main.py` 一致；checks 填 DB/Redis 状态。
2. 容器编排：pgvector 镜像 + init 脚本（vector 扩展）复用现有库；健康检查探针。

**验证**：
- 部署冒烟：`docker compose up -d && curl /health`、`/health/detail` JSON 结构断言。
- **验收**：6.5。

### E3 压测（1d）

**目标**：性能不劣于基线。

**改动文件**：
- `scripts/benchmark/benchmark-http.sh`、`benchmark-sse.sh`（复用 Python 版语义）
- `scripts/benchmark/README.md`

**步骤**：
1. 登录 QPS 压测（≥6.0）；SSE 聊天流时长（对照 15–21s 基线同量级）；并发守卫行为（10 并发 + 429）。
2. 与 Python 版同场景对比记录（写入 `docs/performance-data/java-vs-python.csv`）。

**验证**：
- 压测脚本输出对比表；QPS/时长达标。
- **验收**：7.3。

### E4 端到端 + eval 双回归 + 前端零改动（2d）

**目标**：全流程可用 + 评估不倒退。

**改动文件**：
- `scripts/e2e/`（6 流程脚本，对照 Python tests/e2e）
- `scripts/dual-run.sh`（Python vs Java 同输入双跑 diff）
- `scripts/eval-run.sh`（EVAL_BASE_URL 指向 Java 跑 fixture + retrieval）

**步骤**：
1. 前端仅切换 `VITE_API_BASE` 指向 Java，全流程回归：注册/登录/聊天/规划/修改/历史/知识库/反馈/通勤/管理后台/Token 用量。
2. eval 双回归：fixture pass_rate ≥ Python 基线；检索 Hit@K/MRR ≥ 基线（对照 `eval-reports/baseline.json`）。
3. dual-run 全端点 diff 清零。

**验证**：
- e2e 6 流程脚本全绿；eval 报告对比表（`docs/eval/java-vs-python.md`）。
- **验收**：7.1、7.2。

### E5 CI 流水线（1d）

**目标**：全阶段测试在 CI 全绿 + 双端对拍任务。

**改动文件**：
- `.github/workflows/java-ci.yml`（mvn verify + 契约测试 + 集成测试 + 对拍 job）
- `pom.xml` 测试 profile（testcontainers：PG+pgvector+Redis 或服务化测试库）

**步骤**：
1. CI 分阶段 job：unit → integration（testcontainers）→ contract（双端）→ 对拍（dual-run 抽样）。
2. 对拍 job 需要 Python 服务镜像，标记 manual/scheduled（R12 语义保留）。

**验证**：
- CI 全绿；对拍 job 输出 diff 报告。
- **验收**：7.4。

---

## 6. 验收条目 → 任务映射总表（查漏用）

| PRD 验收 | 覆盖任务 |
|---|---|
| 1.1 | A3 |
| 1.2 | A3 |
| 1.3 | A4 |
| 1.4 | A2, B7 |
| 1.5 | A2(组件), B1, B3, B4, B7 |
| 1.6 | A1 |
| 1.7 | A2 |
| 1.8 | A1, A2 |
| 1.9 | A3 |
| 2.1 | B1 |
| 2.2 | B2, B3, B4, B5, B6 |
| 2.3 | B4 |
| 2.4 | D11 |
| 2.5 | B7, D11 |
| 2.6 | B3 |
| 3.1 | D3(帧格式), D4, D11 |
| 3.2 | D4 |
| 3.3 | D3 |
| 3.4 | D3(15s), D11(3s) |
| 3.5 | D4 |
| 3.6 | D4 |
| 3.7 | D4, D8, D11, E4 |
| 4.1 | D8, D9 |
| 4.2 | D7 |
| 4.3 | D5, D6 |
| 4.4 | D9 |
| 4.5 | B7(机制), D2, D10 |
| 4.6 | D2, D10 |
| 4.7 | D12 |
| 5.1 | C2, C3 |
| 5.2 | C2 |
| 5.3 | C1 |
| 5.4 | C4 |
| 5.5 | A4 |
| 5.6 | C2, C3 |
| 5.7 | C3 |
| 5.8 | C3 |
| 5.9 | C3 |
| 6.1 | E1 |
| 6.2 | D1, D2 |
| 6.3 | D6 |
| 6.4 | C0, E1(降级联动) |
| 6.5 | E2 |
| 7.1 | E4 |
| 7.2 | E4 |
| 7.3 | E3 |
| 7.4 | E5 |

**覆盖完整性**：PRD 全部 47 条验收均有对应任务；无孤岛任务（每任务至少映射 1 条验收）。

---

## 7. 关键里程碑与退出标准

| 里程碑 | 达成条件 | 预估到达（2 人并行） |
|---|---|---|
| M1 基建可用 | A1–A4 全绿：连接现有库、12 表可读写、Redis key 对齐 | 第 2 周 |
| M2 CRUD 契约 | B1–B7 全绿：43 端点中非 AI 部分契约通过 | 第 4 周 |
| M3 RAG 达标 | C0–C4 全绿：Hit@K/MRR ≥ 基线、四路+重排生效、embedding 一致性 ≥0.999 | 第 5 周 |
| M4 Agent 链路 | D1–D12 全绿：chat/recommend 真实 LLM 全事件流 + 四工具升级 + 技能 + 后处理 | 第 7 周 |
| M5 运维与端到端 | E1–E5 全绿：前端零改动、eval 双回归、压测达标、CI 全绿 | 第 8~9 周 |
