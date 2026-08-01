# Trip 后端 Java 重构 PRD（Python FastAPI → Java 21 + Spring Boot 3.3 + langchain4j 1.x）

> **文档状态**：草案 v1.0
> **日期**：2026-08-01
> **范围**：功能面梳理与验收标准（不含实现细节）
> **口径**：功能与 Python 后端**当前线上生效行为** 1:1 复刻；另按主理人指定纳入两项"设计意图补全"：恢复 RAG 四路召回+重排、修复 `password_resets` 表建表遗漏（见 §1.2 G9、§2.4、§4 阶段 1/5）。其余"存在但未启用/未实现"的路径不计入（见 §3 非目标与 §5 风险）

---

## 1. 背景与目标

### 1.1 背景

- 现有后端 `trip-backend/`：Python FastAPI，约 150 个源文件；前端 `trip-front/`（Vue 3 + TypeScript + Naive UI）**本次不改任何代码**。
- 现有基础设施：PostgreSQL 16 + pgvector（`vector`/`pg_trgm` 扩展、`chinese` 全文配置）+ Redis 7；**本次复用现有库与数据，不做数据迁移**。
- 现有 AI 能力栈：LangChain/LangGraph（Python）、DeepSeek/Kimi/Agnes 多 provider、bge-small-zh-v1.5 embedding、BGE-reranker-base、高德 MCP（stdio 子进程）、美团酒旅 CLI。
- 本次目标：用 Java 21 + Spring Boot 3.3 + langchain4j 1.x 重构后端，功能 1:1 复刻，前端零改动、数据零迁移。

### 1.2 可量化验收目标

| 编号 | 目标 | 量化口径 |
|---|---|---|
| G1 | API 契约 100% 兼容 | 43 个 `/api` 端点 + `GET /health`、`GET /health/detail`、`GET /metrics` 全部实现，方法/路径/参数/响应体字段/错误码一致（含 Format A/B、camelCase 与 snake_case 例外端点） |
| G2 | 前端零改动可用 | 前端仅切换 `VITE_API_BASE` 指向 Java 服务即可完整跑通全部页面与流程，无需修改任何前端代码 |
| G3 | 数据零迁移 | 直接连接现有 PostgreSQL 库：12 张表 schema 兼容、pgvector HNSW 索引（m=16, ef_construction=64, cosine）可复用、既有 embedding 数据可直接检索 |
| G4 | 功能行为对等 | chat/recommend/modify/patch 编排、RAG 检索、技能系统、告警、MCP、任务队列的行为与 Python 版对等（以 Python 测试套件 + eval 体系为对照） |
| G5 | 测试对等 | 现有 pytest 测试（49 个测试文件 + tests/e2e 6 个流程）的断言语义等价迁移为 Java 测试；关键测试全绿 |
| G6 | 评估不倒退 | `eval` 体系 fixture 通过率、检索 Hit@K / MRR 不低于 Python 版当前基线（`eval-reports/baseline.json` 为对照） |
| G7 | 性能不劣于基线 | 登录 QPS ≥ 6.0、SSE 聊天流时长与 Python 版同量级（15–21s 基线）、并发守卫行为一致（全局 10 / 单用户 1） |
| G8 | 可观测性对等 | Prometheus 4 类指标（http_requests_total / http_request_duration_seconds / chat_request_duration_seconds / tool_invocations_total）+ `x-request-id` 全链路日志 + 结构化日志 |
| G9 | 设计意图补全（主理人指定） | ①RAG 检索恢复四路召回 + 加权 RRF + credibility 加权重排，检索质量不劣于双路基线（Hit@K/MRR）；②`password_resets` 表由 Java 侧确保创建（12 表 schema 完整），不改动现有表结构与数据 |

---

## 2. 功能范围清单

### 2.1 REST API（模块 A）

统一前缀 `/api`；统一响应 Format B `{code, data, message, error}`（成功 code=200）；**例外**：Format A `{success, data}` 仅 `/api/trip/recommend`（`recommend-stream` 因前缀 startswith 亦命中）；`/api/commute/geocode|inputtips|nearby` 返回裸对象；`/api/commute/optimal` 返回 `{code:0, data, message:"ok"}`。

| 子模块 | 端点 | 认证 | 限流类别 | 要点 |
|---|---|---|---|---|
| 用户认证（7） | `POST /user/register` `POST /user/login` `GET/PUT /user/info` `PUT /user/password` `POST /user/forgot-password` `POST /user/reset-password` | 公开×3 + JWT×3 | auth（10 次/900s） | 注册用户名/邮箱查重；登录支持用户名或邮箱；改密验旧密码；忘记密码恒返回成功防枚举；重置令牌 uuid4 明文入库、30 分钟过期、used 标志；**不发送邮件（仅日志）** |
| 管理后台（3） | `GET /admin/agent-trace/{message_id}` `GET /admin/agent-trace?conversation_id&limit` `GET /admin/mcp-stats` | JWT + Admin（role_id=1） | — | agent 执行步骤明细/摘要；MCP 指标快照（calls/successes/failures/cacheHits/circuitOpenCount/avgDurationMs） |
| 聊天（1） | `POST /trip/chat` | JWT | chat（200/min）+ token 预算 + 并发 | SSE 流式，见 §2.2 |
| 通勤（4） | `GET /commute/geocode` `GET /commute/inputtips` `GET /commute/nearby` `POST /commute/optimal` | 公开 | — | 高德地理编码/联想/周边 POI；多目的地多方式择优（driving/walking/transit/cycling、compare_modes 对比、polyline、has_subway、per_mode） |
| 会话（4） | `GET /conversations`（分页） `GET /conversations/{id}` `POST /conversations` `DELETE /conversations/{id}` | JWT | — | 列表 items/total/page/pageSize；详情含消息（**snake_case 字段**）；创建默认标题；删除级联消息与 agent_steps |
| 反馈（10） | `GET/POST /feedback` `GET /feedback/message/{message_id}`（**公开**） `GET /feedback/stats` `GET /feedback/list/{message_id}` `GET /feedback/admin/high-token-low-satisfaction` `GET /feedback/admin/daily-stats` `POST /feedback/admin/test-alert` `POST /feedback/admin/convert-to-fixture` | JWT（管理类需 Admin） | feedback（30 次/h） | 评分 1/-1、评论截断 500 字、tags≤10 个；**IDOR 校验**（消息归属 + 仅 assistant 消息可评分）；(user,message) 唯一 upsert；admin 端点聚合与告警触发 |
| 行程历史（4） | `GET /history/trips`（分页） `GET /history/trips/{id}` `GET /history/trips/{id}/versions` `DELETE /history/trips/{id}` | JWT | — | content 为完整行程 JSON；versions 返回 V1/V2… 版本链（parent_trip_id）；Trip 无 updated_at |
| 知识库（6） | `GET /knowledge/spots` `GET /knowledge/spots/{id}` `POST/PUT/DELETE /knowledge/spots(/id)` `POST /knowledge/spots/bulk`（**请求体为裸 JSON 数组**） `GET /knowledge/spot-docs` | 公开×3 + Admin×3 | knowledge（100/min） | spots 分页/城市/分类筛选；GET 详情与 POST/PUT 为 **snake_case 响应**；bulk 返回 success/failed 计数；spot-docs 带 chroma:{available, spotDocsCount} |
| Token 统计（3） | `GET /stats/token-usage/summary` `GET /stats/token-usage/stats` `GET /stats/token-usage/logs` | JWT（scope=global 需 role_id==1） | — | summary/stats 返回 `{window:{current, limit, resetAt(ms)}, totalSinceStart}`；logs 返回明细（含 cachedTokens、latencyMs） |
| 行程推荐（4） | `POST /trip/recommend`（Format A） `POST /trip/recommend-stream`（SSE） `POST /trip/{id}/confirm` `POST /trip/{id}/discard` | JWT | recommend（50/min）+ token 预算 + 并发 | recommend 幂等中间件生效；confirm/discard 仅 `status=="candidate"` 可流转到 completed/discarded |

**认证契约**：JWT HS256、有效期 7 天、payload `{userId, username, roleId, exp}`；仅强校验 `userId` 与 `exp`，授权以 DB `role_id` 为准（**不信任 JWT 内 roleId**）；密码 bcrypt **rounds=12**；**缺 Authorization 头 → 403 "Not authenticated"（HTTPBearer 默认），坏/过期 token → 401**（不对称，须保持）。

### 2.2 SSE 事件协议（模块 B）

**端点**：`POST /api/trip/chat`、`POST /api/trip/recommend-stream`。响应头：`Content-Type: text/event-stream`、`Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`。

**帧格式**：`id: {seq}\nevent: {type}\ndata: {JSON}\n\n`；业务事件 seq 从 1 自增；event name = payload 的 `type` 字段；data 含 `type` 本身。

**chat 事件清单**（12 类）：

| 事件 | data 结构 | 时机 |
|---|---|---|
| `stream_meta` | `{type, streamId:"stream:{uuid}"}`，无 id | 首个事件（Redis 可用时），客户端存 localStorage 用于续传 |
| `chunk` | `{type, content}` | LLM 流式增量文本，前端累加 |
| `tool_start` / `tool_end` | `{type, name, key?}`（key 仅 research 路径） | 工具调用起止 |
| `progress` | `{type, data:{stage: research\|plan\|review\|save, status: start\|done, attempt?, duration_ms?, passed?, retry?, mode?, skipped?}}` | 编排各阶段起止 |
| `card` | 三子类：`{type, card_type:"info_text", data:{title, content≤1500}}` / `poi_list` `{data:{items≤10}}` / `commute_compare` `{data:{options≤5, recommended}}` | 工具结果结构化卡片 |
| `trip_planned` | `{type, data:{newTripId, summary}}` | 全量规划完成且新 Trip 落库 |
| `trip_diff` | `{type, data:{newTripId, parentTripId, changes}}` | modify/patch 生成候选行程后 |
| `heartbeat` | `{type:"heartbeat"}` | 流空闲 15s |
| `complete` | `{type, data:{conversationId, usage:{prompt, completion, total, cached}\|null}}` | 终止事件；非旅行拦截路径 usage 全 0 且无 cached |
| `error` | 流内 `{type, error}`（含 type）；请求级 `{error}`（无 type） | 业务错误终止 |
| `end` | `{done: true}`，无 id、无 type | 流正常收尾 |

**终止序列**：成功 = `complete` → `end`；业务错误 = `error` → `end`；底层异常 = 仅 `error`。**前端需同时兼容流内 error（有 type）与请求级 error（无 type）两种形态。**

**recommend-stream 事件**：`start`（含 city/days/budget）→ `progress`（stage: research/plan/review/save）+ `tool_start`/`tool_end`（key: attractions/food/hotels/weather/distance）→ `heartbeat`（空闲 3s）→ `complete`（完整结果）或 `error`。

**断点续传**：请求头 `X-Stream-Id` + `Last-Event-ID`（非负整数）同时存在才触发；服务端重发 `seq > lastSeq` 全部已持久化事件（保留原 id）并追加 `end`；只读重放不改状态。错误映射：400（Last-Event-ID 非法 / lastSeq>totalSeq）、404（stream 不存在/过期）、403（owner 不匹配，IDOR）。Redis StreamStore：`stream:{id}` HASH + `{id}:events` LIST + `{id}:seq` STRING，**TTL 600s**、单事件 ≤64KB、append 续期；Redis 不可用降级内存（不可跨进程续传）。

**落库契约**：user 消息立即落库；assistant 消息先建空行取 id，流式期间**每 3s 增量 flush**，complete/error 强制 flush 并附 `metadata.usage`；标题取首条消息前 20 字符 + "..."（仅当为空/"新对话"）；Agent 轨迹经 TraceRecorder buffer+flush 落 agent_steps；token 统计异步写 token_usage_log；流结束后 arq 入队 `post_chat_followup`（压缩 + 关键决策 + 偏好提取），幂等键 `post_chat:followup:{conversation_id}`。

### 2.3 Agent 能力（模块 C）

**编排主链路**（Python 版已从 LangGraph 图迁移为"纯 asyncio Orchestrator + 多 Agent 对象"，chat_graph/planner_graph 已废弃；Java 侧按编排语义复刻，不绑定图运行时）：

- `AgentEngine` 单例：`chat()`（多轮流式前台）与 `recommend()`（直连 Orchestrator）两条链路；共享 llm / tool_cache / skill_registry / fallback_llm。
- **chat 前台**：ChatAgent 单 Agent ReAct；LLM 工具调用驱动升级——`trigger_plan` → Orchestrator.plan + 落库新 Trip + `trip_planned`；`trigger_modify` → Orchestrator.modify + 落库 v2 candidate（parent_trip_id 版本链）+ `trip_diff`；`trigger_patch` → patch_engine 槽位级修改（replace/remove/swap），失败降级 modify；`select_skill` → 技能执行；其他工具 → 工具卡片。另有 LLM 前预检测（"附近/通勤"关键词直调高德发 card）。
- **recommend 链路**：Orchestrator.plan 三阶段 —— Research（并行 5 工具产出 ResearchBundle）→ Planner（产出 raw_output + parsed）→ review（LLM 审阅，`MAX_REVIEW_RETRIES=2`，失败注入 feedback 重跑 Planner）；最终 `validate_with_repair` 兜底修复。
- **modify 双模式**：局部（target_days 有值，跳过 research、只改指定天、merge 回原行程）与全量（完整 research+plan+review）。
- **工具清单**（10 个业务工具 + 高德 MCP 工具 + 美团）：

| 工具 | 参数 | 用途 | 韧性（timeout/retries/熔断） | 缓存 |
|---|---|---|---|---|
| retrieve_knowledge | query, city, category? | RAG 检索景点/美食/住宿/交通 | 8s / 0 / 5次30s | ttl 300s，embedding 阈值 0.85 |
| search_hotels | city, budget?, level? | 酒店检索 | 10s / 1 / 5次30s | ttl 300s |
| calculate_distance | from_city, to_city, mode? | 城际距离/耗时/费用；car 走高德路网，失败回退 Haversine | 5s / 1 / 5次30s | ttl **3600s** |
| compute_optimal_commute | origin, destinations, mode, city?, compare_modes | 通勤择优 | 20s / 1 / 5次30s | 不缓存 |
| search_commute_tips | keywords, city?, limit | 地名→坐标 | 8s / 1 / 5次30s | 不缓存 |
| search_nearby_commute_pois | lat, lng, radius, keywords?, types?, limit | 周边 POI | 8s / 1 / 5次30s | 不缓存 |
| meituan_query | query, origin_query?, city? | 美团酒旅 CLI（npx ht-ai），沙箱子进程、150s 超时 | 无包装 | 无缓存 |
| trigger_plan / trigger_modify / trigger_patch / select_skill | 见 §2.3 上文 | 升级/修改/技能选择 | 无 | 无 |
| 高德 MCP（maps_weather 等） | MCP schema | 天气/地理等 | 走 MCP guards | TTL 1800s（仅 weather/geo 可缓存） |

**技能系统**：三层披露 L1 目录（name/description/tags，常驻上下文）→ L2 整篇 SKILL.md（选中才读）→ L3 执行（多轮 tool calling，MAX_SKILL_ITERATIONS=10）；加载自 `.claude/skills` 目录；选择由 LLM 绑定 `select_skill` 工具自主判断（关键词粗选为兜底）。

**意图识别**：当前生效方式为 LLM tool calling（trigger_* 工具）；`intent.py` 规则 fast-path 存在但**无调用方**（不计入复刻，见非目标）。

**韧性**：熔断（连续失败 ≥5 → OPEN，30s 后半开，试错成功恢复；CLOSED 下成功不重置失败计数）；重试（429 优先 Retry-After，封顶 30s，否则指数退避 2^n 封顶 10s）；工具失败返回 fallback 文案（不抛）；Planner 主 LLM 失败切换 fallback_llm；embedding fail-closed。

**Token 预算与监控**：用户 50K/小时、全局 200K/分钟（滑动窗口）；入口守卫超限返回 **429（用户）/503（全局）**；LLM 每次 on_llm_end 记账 + 环形缓冲监控（1000 条、告警阈值 100K）+ 落库 token_usage_logs。

**并发控制**：全局 `Semaphore(10)` + 每用户 `Semaphore(1)`，非阻塞获取，超限 **429**；流式端点 finally 释放。

**后处理**：`post_chat_followup`（对话压缩 → 关键决策 → LLM 偏好提取合并进 User.preferences）。

### 2.4 RAG 与知识检索（模块 D）

**数据模型**：`spot_docs` 表 —— `embedding Vector(512)`（bge-small-zh-v1.5）+ HNSW 索引（m=16, ef_construction=64, cosine）；可信度字段 authority/freshness/agreement/citation_count/evidence_density/credibility_score；`spots` 表同维 embedding + `(city, category)` 索引。

**检索流水线（Python 版当前生效路径，恢复前基线）**：query 改写（清洗 + 停用词提取 + city 前缀）→ 双路召回（`rating` 排序 + pg 全文检索 `to_tsvector('chinese', name||' '||description) @@ websearch_to_tsquery('chinese', q)`）→ 加权 RRF 融合（公式 `weight/(k+rank)`，k=60，权重 **pg_fulltext=0.7 / rating=0.5**，credibility 乘数 `(0.5+cred)`）→ 截断返回（limit=5）。全文失败降级 LIKE；RRF 加权失败降级普通 RRF。

**设计意图补全（本次纳入范围）**：恢复 Python 版中被注释跳过的两条向量召回路径与重排（原注释"依赖 Embedding 模型不稳定，临时跳过"）：
- spots 向量召回（`_pgvector_search`）：cosine 相似度、`embedding IS NOT NULL` 过滤、city/category 过滤；
- spot_docs 向量召回（`_spot_docs_search`）：JOIN spots 按 city 过滤，向量失败降级全文再聚合；
- credibility 加权重排（`rerank_with_credibility`）：BGE-reranker-base CrossEncoder 打分 + sigmoid 归一化，`final=(1-w)*rerank + w*cred`，w=0.3；模型不可用/失败降级原始顺序。
- **恢复后流水线** = 改写 → **四路召回**（rating + pg_fulltext + spots 向量 + spot_docs 向量）→ 加权 RRF（k=60；既有两路权重 0.7/0.5 保持不变，新增两路权重以配置项给出、以检索回归调优为准）→ credibility 加权重排 → 截断返回（limit=5）。
- **降级语义保留**：embedding fail-closed 时向量两路自动跳过回到双路；rerank 不可用降级原始顺序；检索链路始终可用。

**LLM 查询改写不纳入范围**（Python 版亦未实现，维持非目标）。

**Embedding**：bge-small-zh-v1.5、512 维、查询前缀「为这个句子生成表示以用于检索相关文章：」、batch_size=32、40s 超时；**fail-closed**（启动标记不可用，后台预热成功才恢复向量检索；期间检索走 rating+全文两路）。

**知识库 CRUD**：spots 增删改查（分页/城市/分类）、bulk 导入、spot-docs 列表（city/source_type 过滤 + chroma 状态）；create/update/bulk 后入队 embedding 同步。

**缓存**：poi_cache（`poi:{city}:{category}:{query_hash}`，TTL 3600s，仅 attraction/food，Redis 优先内存降级）；llm_cache（SHA-256 prompt hash，TTL 600s）；tool_cache（`tool_cache:{tool}:{key}`，字面 key 或 embedding 相似度 ≥0.85 命中，TTL 300–3600s）。

**后台任务**：`embedding_sync`（spots create/update/bulk 后异步算 embedding 覆盖写）；`wiki_fetch`（脚本驱动逐城抓维基写 `wiki_raw/{city}.json`，再经 ingest_spot_docs 转 spot_docs）。

**降级链**：embedding 不可用 → 跳过向量路径 → 全文失败 → LIKE → RRF 加权失败 → 普通 RRF → arq 不可用 → asyncio 内存任务 → Redis 不可用 → 内存缓存。

### 2.5 基础设施（模块 E）

**中间件链**（执行顺序外→内，须保持）：Prometheus → RequestID → Idempotency → GlobalRateLimit → CORS → GZip → 路由。形态要求：**不缓冲响应体**（兼容 SSE；幂等中间件为 BaseHTTPMiddleware 且消费 body，因此**只应用于 `/api/trip/recommend`**，不可用于 chat）。

**限流**：固定窗口算法；6 个实例（全局 2000/60s 按 IP、auth 10/900s、chat 200/60s、recommend 50/60s、feedback 30/3600s、knowledge 100/60s）；Redis INCR+EXPIRE，降级内存；超限 429，响应头 `X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset`（**绝对 Unix 时间戳**，无 Retry-After）；key 为用户 id 优先、否则客户端 IP。

**幂等**：仅 `/api/trip/recommend` POST；key = `{userId or anonymous}:{idempotency-key 请求头}`（不含 body hash）；**进程内存存储**、TTL 3600s、只缓存 2xx JSON 响应、命中返回缓存体（原响应头丢失）。

**指标**：`http_requests_total{method,path,status}`、`http_request_duration_seconds{method,path}`（0.005–10s buckets）、`chat_request_duration_seconds`（0.1–60s）、`tool_invocations_total{tool,status}`；排除 /metrics 与 /health。

**异常映射**：自定义异常（NotFound 404 / Unauthorized 401 / Forbidden 403 / BadRequest 400 / Conflict 409）；IntegrityError → 409 DUPLICATE_ENTRY / 400 FOREIGN_KEY_VIOLATION / 400 INTEGRITY_ERROR；JWT 失效 → 401；DB 错误 → 500（dev 泄漏、prod 隐藏）；兜底 500。Format A/B 判定按 `/api/trip/recommend` 前缀。**注意：auth/限流/守卫抛的 HTTPException 不经这些 handler，保持 `{"detail":...}` 包装。**

**数据层**：12 张表（roles/users/password_resets/trips/conversations/messages/spots/spot_docs/feedbacks/agent_steps/token_usage_logs）；JSONB 语义列：users.preferences、messages.metadata、trips.content、spots.tags；ondelete 行为（messages 级联、token_usage_logs SET NULL 等）；连接池 10/overflow 20；启动时幂等启用 vector 扩展 + 慢查询日志（阈值 100ms）。
**schema 完整性（补全）**：Python 版 `create_tables.py` 漏建 `password_resets` 表；Java 侧启动时校验 12 表齐全，缺失表幂等补建（字段/约束与 `models/password_reset.py` 一致：email、token 唯一、expires_at、used），**不改动现有表结构与数据**。

**Redis 用途总清单**：限流计数、SSE 流续传（600s）、tool_cache、poi_cache（3600s）、llm_cache（600s）、research_bundle（300s）、arq 任务结果（3600s）。幂等与 MCP 缓存为进程内存（多实例不共享）。

**任务队列**：arq 双后端（Redis 可用 → arq，否则 asyncio 内存降级）；7 个 worker 函数（embedding_sync×2、post_chat_followup、fetch_city_wiki、demo×3）；`max_tries=3`（指数退避 1/2/4s）、job_timeout=300s、keep_result 3600s；job_id 即幂等键。

**告警系统**：周期 300s 检测（窗口 60min、满意率 = up/(up+down)、条件 total≥5 且 rate<0.5）→ MD5 指纹去重（冷却 3600s）→ webhook（feishu/slack/dingtalk/wecom/custom 5 种 payload；失败重试 3 次退避 1/3/9s）；`alert_enabled=false` 默认关闭。

**LLM Provider 路由**：deepseek/kimi/agnese 三 provider；健康状态 HEALTHY/DEGRADED/DOWN（连续失败 3/5 次，60s 自动恢复窗口）；场景优先级 PLANNING=[deepseek,kimi,agnese]、CHAT=[agnese,kimi,deepseek]、RESEARCH=[agnese,deepseek,kimi]；`call_with_fallback` 15s 超时 → 记失败 → 切 fallback。

**高德 MCP**：stdio 子进程（npx @amap/amap-maps-mcp-server）+ JSON-RPC 2.0；guards：熔断（fail_max=5, reset 60s）、令牌桶限流（3/s, capacity 5）、缓存（TTL 1800s，仅 weather/geo 可缓存）；指标快照供 `/api/admin/mcp-stats`。

**部署**：docker-compose 三服务（app/postgres+pgvector/redis）；Java 侧对应服务编排 + 健康检查 + `/health` 与 `/health/detail` 语义保留。

---

## 3. 非目标（明确不做）

| # | 非目标 | 理由 |
|---|---|---|
| N1 | 不修改任何前端代码 | 硬约束：前端仅切换 API 地址 |
| N2 | 不迁移/重建数据库数据 | 复用现有 PG + pgvector + Redis；schema 以现有库为准，不因 Python 侧缺陷而改表 |
| N3 | 不复刻"设计存在但当前未生效"的其余代码路径 | `intent.py` 规则意图识别（无调用方）、LLM 查询改写（未实现）；**例外**：RAG 四路召回+重排、`password_resets` 建表已按主理人指定纳入范围（见 G9、§2.4、§2.5） |
| N4 | 不复刻 Python 侧其余已知缺陷 | `convert-to-fixture` stub（恒返回 "Not implemented yet"）、密码重置不实际发邮件（仅日志） |
| N5 | 不做多实例横向扩展改造 | 幂等存储、MCP 缓存、并发信号量为进程内存语义，保持与 Python 版一致的单实例行为 |
| N6 | 不做性能优化专项 | 以"不劣于基线"为准，不引入 Python 版没有的新缓存/新架构 |
| N7 | 不新增端点/不删除端点 | 契约以 Python 版现行清单为准，避免前端契约漂移 |
| N8 | 不引入向量数据库替代 pgvector、不替换高德/美团外部依赖 | 复用现有基础设施与第三方能力 |

---

## 4. 验收标准（按迁移模块分阶段）

> 每阶段验收均为**可执行测试**；基线对照 = Python 版测试套件（tests/ 49 文件 + e2e/ 6 流程）+ eval 体系（fixture pass_rate、Hit@K/MRR）+ docs/performance-data/ 基准。

### 阶段 1：基础设施与数据层
| # | 验收条目 | 验证方式 |
|---|---|---|
| 1.1 | 直接连接现有 PostgreSQL：12 张表可读，pgvector 扩展与 HNSW 索引存在且可查询 | 连接现有库执行 `SELECT` 与向量 `<=>` 查询；对比 `\d` schema |
| 1.2 | 全部 JSONB 语义列（preferences/metadata/content/tags）读写一致 | 单测：往返序列化断言 |
| 1.3 | Redis 全部 key 前缀（限流/stream/tool_cache/poi_cache/llm_cache/research_bundle/arq）语义一致 | 单测 + 集成测试比对 key 格式与 TTL |
| 1.4 | 中间件执行顺序与不缓冲要求一致 | 集成测试：SSE 端点不被缓冲；幂等仅作用于 recommend |
| 1.5 | 限流器 6 实例阈值/窗口/响应头（含 X-RateLimit-Reset 绝对时间戳）一致 | 参数化单测覆盖每个实例 |
| 1.6 | 异常映射全表（404/401/403/400/409/500 + Format A/B + `{"detail"}` 例外）一致 | 单测逐条断言状态码与响应体 |
| 1.7 | Prometheus 4 类指标名/label/bucket 一致，/metrics 可抓取 | 抓取断言指标存在 |
| 1.8 | `x-request-id` 透传/回写/日志贯穿 | 集成测试断言响应头与日志 |
| 1.9 | `password_resets` 表由 Java 侧幂等创建，schema 与 Python `models/password_reset.py` 一致（token 唯一、expires_at、used）；其余 11 张表结构与数据不被改动 | 对空库跑启动校验自动补建并 `\d password_resets` 断言；对现有库跑校验为幂等 no-op，前后数据行数不变 |

### 阶段 2：REST API 业务模块（非 AI）
| # | 验收条目 | 验证方式 |
|---|---|---|
| 2.1 | 认证 7 端点契约全兼容（含 bcrypt rounds=12 兼容现有密码、403/401 不对称语义、忘记密码防枚举、重置令牌 30min/used） | 对照 Python 测试语义的 Java 测试全绿 |
| 2.2 | 会话/历史/知识库 CRUD/反馈/统计/管理/通勤 全部端点：方法/路径/参数/响应字段（含 camelCase 与 snake_case 例外）/错误码一致 | 逐端点契约测试；Python 侧同输入断言输出字段集一致 |
| 2.3 | 反馈 IDOR 防护与 upsert 语义一致 | 权限单测 |
| 2.4 | 行程 confirm/discard 状态机（candidate→completed/discarded）一致 | 状态机单测 |
| 2.5 | `/api/trip/recommend` 幂等语义（同 idempotency-key 重复请求返回缓存）一致 | 集成测试 |
| 2.6 | 知识库 bulk 裸数组请求体、spot-docs 的 chroma 状态字段一致 | 契约测试 |

### 阶段 3：SSE 与聊天链路
| # | 验收条目 | 验证方式 |
|---|---|---|
| 3.1 | chat SSE 12 类事件 + recommend-stream 事件：事件名/帧格式/seq 自增/data 字段结构逐一对齐 | 协议测试解析字节流比对事件序列（对照 Python 测试同用例输出） |
| 3.2 | 终止序列（complete→end / error→end / 仅 error）一致 | 协议测试三路径 |
| 3.3 | 断点续传：X-Stream-Id + Last-Event-ID 重放、403/404/400 错误、只读不重放状态 | 集成测试（含 Redis TTL 600s） |
| 3.4 | 心跳 15s（chat）与 3s 空闲（recommend-stream）语义一致 | 协议测试 |
| 3.5 | assistant 消息 3s 增量 flush、complete 附 usage、标题截断 20 字符规则一致 | 落库断言 |
| 3.6 | 非旅行问题短路路径（chunk→complete usage 全 0→end）一致 | 协议测试 |
| 3.7 | 前端实测：Chat 页、TripGenerating 页、断线重连在 Java 服务下无改动可用 | 前端联调冒烟（人工/脚本） |

### 阶段 4：Agent 编排
| # | 验收条目 | 验证方式 |
|---|---|---|
| 4.1 | chat 升级路径：trigger_plan/trigger_modify/trigger_patch/select_skill 四工具触发与降级（patch 失败→modify）行为一致 | 用 mock LLM 的确定性工具调用测试 |
| 4.2 | Orchestrator：research→plan→review 三阶段、MAX_REVIEW_RETRIES=2 重试循环、modify 局部/全量模式、validate_with_repair 兜底 | 编排单测（对照 test_agent_engine 语义） |
| 4.3 | 10 个业务工具参数/输出/韧性（timeout/retries/熔断/fallback 文案）与缓存策略（ttl/embedding 阈值）逐一对齐 | 工具级单测 + tool_cache 命中测试 |
| 4.4 | 技能系统 L1/L2/L3 披露、select_skill 选择、MAX_SKILL_ITERATIONS 循环 | 技能测试（对照 test_skills_foundation / test_skill_itinerary） |
| 4.5 | token 预算守卫（用户 429 / 全局 503）、并发守卫（全局 10 / 单用户 1，超限 429，finally 释放） | 并发与预算测试 |
| 4.6 | Agent 轨迹 agent_steps 落库、token_usage_logs 落库 | 集成断言 |
| 4.7 | post_chat_followup（压缩/关键决策/偏好提取）幂等键与效果一致 | 任务测试 |

### 阶段 5：RAG 与知识检索
| # | 验收条目 | 验证方式 |
|---|---|---|
| 5.1 | 检索流水线（改写→四路召回→加权 RRF→credibility 加权重排→截断 5 条）结果与恢复后目标行为一致；双路基线作为对照 | 同一查询集双端对比 top 结果（对照 eval/retrieval 数据集），并记录双路 vs 四路差异 |
| 5.2 | 检索 Hit@K / MRR 不低于 Python 版基线 | 跑 `eval/retrieval` 语义等价物，对比 baseline |
| 5.3 | embedding fail-closed 行为：不可用时检索降级两路、预热恢复后向量可用 | 故障注入测试 |
| 5.4 | spots CRUD/bulk 后的 embedding 同步任务幂等与覆盖写一致 | 任务测试 |
| 5.5 | poi_cache / llm_cache / tool_cache 的 key、TTL、命中与降级一致 | 缓存测试 |
| 5.6 | 降级链（全文→LIKE→普通 RRF→内存任务→内存缓存）逐级触发 | 故障注入测试 |
| 5.7 | 四路召回+重排实际生效：spots/spot_docs 向量两路被调用、rerank 排序生效、credibility 加权（w=0.3）参与最终排序 | 指标/日志断言四路调用次数；对比"双路 vs 四路"top-N 结果集差异 |
| 5.8 | 四路召回质量回归：Hit@K / MRR ≥ Python 版双路基线，且不低于恢复前实测 | 检索评估（eval/retrieval 语义等价物）对比基线 |
| 5.9 | 恢复后降级语义：embedding 不可用自动回到双路；rerank 不可用降级原始顺序；检索始终可用 | 故障注入测试 |

### 阶段 6：外围系统
| # | 验收条目 | 验证方式 |
|---|---|---|
| 6.1 | 告警检测/去重/调度/webhook 5 种 payload 与 Python 版一致 | 用测试告警端点触发，断言 webhook 请求体 |
| 6.2 | provider 健康检查（3/5 次失败降级、60s 恢复）与场景优先级、15s failover | 故障注入测试 |
| 6.3 | 高德 MCP 子进程启动/就绪/调用、guards（熔断 5/60、令牌桶 3/s、缓存 1800s）、mcp-stats | 冒烟 + 指标断言 |
| 6.4 | 任务队列降级（Redis 不可用 → 内存）与幂等键 | 故障注入测试 |
| 6.5 | /health、/health/detail 语义与部署编排（docker-compose 等价物）就绪 | 部署冒烟 |

### 阶段 7：端到端验收
| # | 验收条目 | 验证方式 |
|---|---|---|
| 7.1 | 前端零改动全流程走通（注册/登录/聊天/规划/修改行程/历史/知识库管理/反馈/通勤/管理后台/Token 用量） | 前端联调回归（对照 e2e/ 6 个流程） |
| 7.2 | eval fixture 通过率 ≥ Python 版当前基线 | 双端跑同一 eval 集对比 |
| 7.3 | 性能不劣于基线（登录 QPS≥6.0、SSE 流时长同量级、并发守卫行为一致） | 压测脚本（benchmark-http / benchmark-sse 等价物） |
| 7.4 | 全部阶段 1–6 测试在 CI 全绿，且与 Python 版同用例输出一致 | CI 流水线 |

---

## 5. 风险与对策

| # | 风险 | 等级 | 影响面 | 对策 |
|---|---|---|---|---|
| R1 | **SSE 被中间件/框架缓冲**：GZip、BaseHTTPMiddleware 形态中间件会延迟或破坏流式输出 | 高 | 模块 B/C | 保持"不缓冲"中间件形态约束；SSE 端点禁用压缩/缓冲；联调冒烟测试覆盖心跳与断线 |
| R2 | **langchain4j 1.x 对 ReAct/tool calling 语义的差异**：Python 版依赖 stream_options include_usage、tool_call 分派、多轮 tool loop、LLM 工具自主选择（trigger_*），langchain4j 的 AiServices/StreamingChatLanguageModel 能力映射不完整 | 高 | 模块 C | 按"编排语义"而非"API 形态"复刻；先做 LLM 流式+工具调用的 spike，锁定差异清单再铺开 |
| R3 | **embedding 模型 Java 侧加载**：bge-small-zh-v1.5 为 sentence-transformers 生态，Java 无原生等价加载路径，且要求与现有库中已写入的向量语义一致（否则检索质量漂移） | 高 | 模块 D | 评估 ONNX Runtime 导出模型或旁路 Python embedding 服务；用现有库 embedding 数据做余弦一致性回归（抽样比对） |
| R4 | **pgvector 与 JPA/Hibernate 集成**：`vector(512)` 列与 HNSW 索引需要原生 SQL/自定义类型映射，ORM 层默认不支持 | 高 | 阶段 1/5 | 向量操作走原生 SQL（JdbcTemplate/原生查询），ORM 实体仅映射标量列 |
| R5 | **中文全文检索语义**：Python 侧实际用 `chinese` 配置（COPY=simple，非真 zhparser），无 GIN 索引、运行时 to_tsvector；Java 侧需保证 SQL 逐字一致 | 中 | 模块 D | 直接复用同一套 SQL 语句与 DB 配置，不做"改进"（列入 N4 口径）；回归测试对比双端结果 |
| R6 | **契约细节陷阱**：HTTPBearer 缺头 403/坏 token 401 不对称；X-RateLimit-Reset 为绝对时间戳；Format A/B 与 snake_case 例外端点；`{"detail"}` 包装例外 | 中 | 模块 A/B | 将全部例外整理为契约测试用例清单，逐条断言（阶段 2 验收 2.1/2.2 覆盖） |
| R7 | **断点续传与并发守卫的语义**：StreamStore TTL 600s、IDOR 校验、全局 10/单用户 1 信号量与 Spring 线程模型（虚拟线程 vs 平台线程）的映射 | 中 | 模块 B/C | 信号量语义用独立组件复刻（不依赖框架线程池行为）；续传做集成测试 |
| R8 | **复刻边界争议**：Python 端"存在但未启用"的其余代码（规则意图、LLM 改写）与缺陷（stub、不发邮件）是否复刻 | 中 | 全模块 | 本 PRD 已按"当前生效行为 + 两项指定补全"定义范围（§3 N3/N4、§1.2 G9）；实施前与干系人确认口径，形成会议纪要 |
| R13 | **恢复四路召回+重排改变检索行为**：由双路变四路并引入 rerank 后，检索 top-N 与对话输出可能变化，存在评估指标波动风险 | 高 | 模块 D | 恢复路径以配置开关隔离（可一键回退双路）；以检索评估（Hit@K/MRR）与对话 eval 双回归为放行条件；新增两路权重与 w=0.3 可调 |
| R14 | **password_resets 建表与现有库差异**：现有库可能从未建过该表，也可能已用不同 DDL 存在 | 中 | 阶段 1 | 实施前对现有库实测该表状态；补建采用幂等 IF NOT EXISTS 语义；不触碰其余 11 张表 |
| R9 | **多 provider failover 与 token 统计差异**：15s 超时 failover、场景优先级、usage 统计（cached 键）需与 Python 版一致 | 中 | 模块 C/E | 对照 router.py/llm.py 语义做故障注入测试；usage 上报结构逐字段断言 |
| R10 | **高德 MCP stdio 子进程管理**：Java 侧 spawn `npx @amap/amap-maps-mcp-server` + JSON-RPC 2.0 握手与就绪探测的时序差异 | 中 | 模块 E | 进程生命周期（启动/就绪/熔断/重启）做冒烟与指标测试；复用 guards 语义 |
| R11 | **性能不劣于基线**：JVM 冷启动、首次 embedding/rerank 加载、SSE 并发吞吐 | 低 | 全局 | 阶段 7 压测对比；预热机制（embedder warmup 等价物）纳入启动流程 |
| R12 | **eval 体系可移植性**：Python eval 工具（LLM-as-Judge、fixture runner）需在 Java 侧有等价执行通道 | 中 | 验收 G6 | eval 驱动层可保留 Python 脚本对 Java 服务发起真实请求（EVAL_BASE_URL 指向 Java），仅业务代码用 Java 重写 |

---

## 附：信息梳理依据（供实施参考，不属 PRD 范围）

- 契约来源：trip-backend/src 全量通读（controllers/schemas/middleware/models/config/services 各子包），含 `main.py` 中间件链与 lifespan、`settings.py` 全部配置项。
- 前端约束：trip-front/src/api/* 调用面与后端 10 个 controller 一一对应；`request.ts` 兼容 Format A/B；SSE 经 `fetchStream` 消费。
- 测试基线：tests/（49 文件，覆盖中间件/控制器/服务/Agent/RAG/技能/任务）+ tests/e2e/（6 流程）+ eval/（fixture runner + retrieval Hit@K/MRR + ragas）。
