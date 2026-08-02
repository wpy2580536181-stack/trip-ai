# 项目讲解文档（Interview Guide）

> 面试准备用 · 以当前代码（`README.md` + `trip-backend/src/`）为准
> 目标：1.5-2 小时讲完整个项目
> 配套：`docs/agent-interview-gap-analysis.md`（岗位差距分析 + 补强路线）

## 目录

- [Part 1 — 项目总览](#part-1--项目总览)（5 分钟）
- [Part 2 — 4 个核心亮点 STAR](#part-2--4-个核心亮点-star)（30 分钟）
- [Part 3 — 12 个高频问题预演答案](#part-3--12-个高频问题预演答案)（30 分钟）
- [Part 4 — Trade-off 论述](#part-4--trade-off-论述)（10 分钟）

---

## Part 1 — 项目总览

### 一句话定位

**trip-ai 是一个 AI 旅行规划助手**：用户说一句"想去北京玩 3 天预算 5000"，Agent 自动经 LangGraph 工作流调用工具链（知识检索 / 距离计算 / 酒店查询 / 高德 MCP POI）生成结构化行程 JSON，chat 全程 SSE 流式输出并支持断点续传。

### 技术栈一览（真实）

| 层 | 选型 | 备注 |
|---|---|---|
| 前端 | Vue 3.5 + TypeScript + Vite 8 + Naive UI + vue-router 4 | 自研 SSEParser 处理流式 |
| 后端 | **FastAPI + Uvicorn（Python ≥ 3.12）** | 工厂模式 `create_app()`，统一 `/api` 前缀 |
| Agent 框架 | **LangChain + LangGraph（StateGraph）** | ChatGraph + PlannerGraph 双状态图 |
| 数据库 | MySQL 8（**SQLAlchemy 2.x async** + aiomysql）+ Redis 7 + ChromaDB | Redis 存流/缓存/限流；Chroma 存向量 |
| LLM | **DeepSeek `deepseek-chat`（主）+ Kimi `moonshot-v1-8k` / Agnes（备，主备自动切换）** | `streaming=True`，回传 token 用量 |
| Embedding | **bge-small-zh-v1.5**（本地，384 维） | 查询加检索前缀 |
| 重排序 | **bge-reranker-base**（Cross-Encoder，top-20） | 高分命中可跳过重排 |
| 可观测 | structlog（JSON + 敏感字段脱敏）+ request_id 全链路 | 自研 Agent trace 对标 LangSmith |

> ⚠️ 说明：本项目后端是 **Python/FastAPI**，不是 Node/Express。历史文档若提到 Express/Prisma/Pino 均已废弃，以本文与代码为准。

### 4 个核心能力

1. **AI Agent 编排** — LangGraph 双图（ChatGraph 路由 + PlannerGraph 规划）+ 本地工具链 + 高德 MCP + ReAct AgentExecutor（legacy_agent）
2. **RAG** — 三路召回（Chroma 向量 / MySQL 关键词 / 评分）+ RRF 融合 + Cross-Encoder 重排
3. **流式 chat** — SSE + Redis + `Last-Event-ID` 断点续传
4. **评估体系** — 三层评估（检索 Hit@K/MRR + 生成 Faithfulness/Relevancy + 线上反馈）+ 10 fixture + LLM-as-Judge

### 数据 / 规模

| 指标 | 数值 |
|---|---|
| 知识库 POI | **30,791 条，覆盖 153 城** |
| 数据来源 | 手工整理 + 高德 API 批量拉取；MCP 实时补充千万级全库 POI |
| 检索链路 P50 | **~640ms**（三路召回 + RRF + 重排） |
| Embedding | bge-small-zh-v1.5（384 维，~50ms/次） |
| 向量存储 | ChromaDB（~23 MB） |
| Eval fixture | 10 个（YAML）|
| 评估器 | domain / general / multi_turn / ragas 四类 |

> 性能压测数字（QPS / SSE P99 / cache 命中率等）请以最新一次针对当前 FastAPI 后端的压测为准（见 `docs/performance-benchmark.md`）；如久未重跑，面试前建议重测一次再引用。

---

## Part 2 — 4 个核心亮点 STAR

### 亮点 1：断点续传流式 Agent

**S**ituation
用户流式收 AI 回复到一半时（网络断/刷新/切后台）会丢失已收内容，整段重传浪费 token 和等待时间。

**T**ask
设计带断点续传的流式 Agent，客户端断线后能精确从断点续传，不丢 chunk、不重复 chunk。

**A**ction
1. **客户端 SSE**（原生自动重连 + `Last-Event-ID` 头）+ 自研 `SSEParser`（累加式处理 chunk 边界，指数退避封顶 16s）
2. **服务端给每个 chunk 加 `id:` 序号**（SSE 标准），重连时浏览器自动带 `Last-Event-ID`
3. **Redis 双写 stream 持久化 sequence**，断线用 `Last-Event-ID` 从 Redis 续推；含 **IDOR 防护**（userId 校验）
4. 边界处理：agent 中断时工具还在跑 → 服务端等工具完成后续推；重复 chunk → 客户端按 eventId dedup

**R**esult
- 续传延迟低（Redis 命中）
- 节省大量重复 token（不再整段重传）
- 代码：`trip-backend/src/utils/stream.py`、`trip-front/src/api/stream-parser.ts`

---

### 亮点 2：可视化 Agent 调试（Agent Trace）

**S**ituation
Agent 内部状态不可见，线上出 bug 定位靠 grep 日志，看不到"调了哪些 tool、参数是什么、返回是什么、每步耗时"。

**T**ask
做类似 LangSmith 的生产级调试工具，admin 能在浏览器回放任意一次 agent 决策。

**A**ction
1. **TraceRecorder** 记录每步：`messageId + step + type + name/args/output/durationMs`
2. **agentEngine 集成钩子**：`on_tool_start` / `on_tool_end` / `complete` / `error`（基于 LangChain `astream_events`）
3. **admin 鉴权**：路由守卫 + 角色校验 + 前端 `beforeEach`
4. **structlog** 全链路 request_id 透传，敏感字段（password/token/api_key/Bearer/sk-）自动 REDACTED

**R**esult
- 1 次 chat 可看到多个 step（含工具调用 + complete）
- API：`GET /api/admin/agent-trace`（admin 守卫）；另有 `/api/admin/mcp-stats` 监控 MCP 进程
- 代码：`trip-backend/src/utils/logger.py`、`services/agent/agent_engine.py`

---

### 亮点 3：反馈 → fixture 自动化闭环

**S**ituation
评估 fixture 不会自动进化，线上用户 👍/👎 反馈被记录但没回流到评估系统，人工维护 fixture 追不上真实问题。

**T**ask
admin 一键把失败案例转成评估 fixture，下次 eval 自动覆盖。

**A**ction
1. **fixtureConverter**：feedback → YAML fixture skeleton
2. **冲突处理**：文件存在追加序号 / 版本升级 / 跳过
3. **API + 前端**：`POST /api/feedback/admin/convert-to-fixture`（admin 守卫）+ Dashboard 转 fixture 按钮
4. **Runner 扫 `eval/fixtures/**/*.yaml`**，反馈闭环让 fixture 自动进化

**R**esult
- 线上反馈直接驱动评估用例增长
- 配套 admin 统计：`/api/feedback/admin/daily-stats`（趋势）、`/api/feedback/admin/high-token-low-satisfaction`（高分低满意度案例）
- 代码：`trip-backend/src/services/feedback*`、`eval/fixtures/`

---

### 亮点 4：三层 RAG 评估体系

**S**ituation
只有主观感觉"行程还行"，没有量化指标证明检索/生成质量，面试被问"怎么评估"只能空谈。

**T**ask
建立覆盖检索、生成、线上三个维度的评估体系，指标可量化、可复现、可 CI。

**A**ction
| 层级 | 指标 | 实现 |
|---|---|---|
| 检索层 | Hit@K（K=1/3/5/10/20）、MRR | `eval/retrieval/`，量化召回与排序 |
| 生成层 | Faithfulness、Answer Relevancy | **LLM-as-Judge**（DeepSeek，temp=0），衡量幻觉与相关性 |
| 线上 | 点赞/点踩率、高分低满意度 | 复用 Feedback 系统追踪真实体验 |

- 评估器分四类：`domain.py` / `general.py` / `multi_turn.py` / `ragas.py`
- 10 个 YAML fixture 描述场景，支持 mock / 真实后端 / CI 多模式

**R**esult
```bash
cd trip-backend
uv run python -m eval.run                    # Agent 评估（mock）
uv run python -m eval.run --real --tag smoke  # Agent 评估（真实后端）
uv run python -m eval.retrieval.run           # 检索层评估
```
- 代码：`trip-backend/eval/`、`eval/evaluators/`、`eval/retrieval/`

---

## Part 3 — 12 个高频问题预演答案

### Q1：介绍一下你的项目？

trip-ai 是 AI 旅行规划助手。后端 FastAPI（Python 3.12+），Agent 基于 LangChain + LangGraph 双状态图（ChatGraph 做路由、PlannerGraph 做规划）。核心 4 能力：LangGraph 编排 + 工具链（本地工具 + 高德 MCP）、三路召回 RAG、SSE 断点续传、三层评估体系。知识库 30,791 POI 覆盖 153 城。LLM 用 DeepSeek 主 + Kimi/Agnes 备，主备自动切换、流式输出并回传 token 用量。
**引用**：`README.md`、`trip-backend/src/main.py`

### Q2：RAG 链路里你做了什么优化？

链路：query → 本地关键词改写 → **三路并行召回**（Chroma 向量 bge-small-zh / MySQL FULLTEXT 关键词 / MySQL 评分排序）→ **RRF 融合**（k=60，支持加权）→ **Cross-Encoder 重排**（bge-reranker-base，top-20）→ 注入 prompt。3 个优化：(1) 本地关键词提取替代 LLM 改写，省 ~800ms；(2) 高分命中直接跳过重排；(3) P50 压到 ~640ms。
**引用**：`trip-backend/src/services/knowledge_service.py`、`rag/rrf.py`、`rag/reranker.py`

### Q3：Agent 怎么决定调哪个工具？

两条路径：(1) **规划路径**（PlannerGraph 的 research 节点）是确定性并行扇出，同时调多路工具拿情报——可控、可追踪；(2) **通用路径**（legacy_agent）用 LangChain `AgentExecutor` 走标准 **ReAct**，LLM 自主决定调哪个工具。工具分两类：LangChain `@tool`（retrieve_knowledge / calculate_distance / search_hotels，统一包超时重试降级 + 缓存）和高德 **MCP**（自研 stdio JSON-RPC 客户端，含熔断/限流/缓存）。
**引用**：`services/agent/nodes/research.py`、`nodes/legacy_agent.py`、`services/mcp/amap_client.py`

### Q4：ReAct 里工具结果用什么角色回传？

用 **user 角色**回传。因为 tool_response 是外部系统返回的内容，不是模型生成的；若放 assistant 角色，模型会误以为是自己说的，后续推理会乱。LangChain AgentExecutor 内部按 ToolMessage 处理，语义上等价于以观察（Observation）身份回灌。
**引用**：`nodes/legacy_agent.py`

### Q5：上下文怎么管理不会超 token？

3 层：(1) **token 预算 + compaction 触发**（`needs_compaction`）；(2) **分层**——近期消息全量 + 历史 LLM 摘要 + 对话脉络 recap；(3) **单调追加、保留 prefix** 以命中 DeepSeek Prompt Cache。用户画像（travel_style/budget/pace/interests）从 DB 注入系统提示。
**引用**：`services/conversation_service.py`、`services/agent/agent_engine.py`、`system_prompt.py`

### Q6：LLM 输出不稳定你怎么处理？

PlannerGraph 的 `validate` 节点做**三级自愈**：(1) **L1 JSON 修复**（正则去 markdown/尾逗号、单引号转双引号，不耗 token）；(2) **L2 Schema 校验**（失败触发 `retry_planner` 重试）；(3) **L3 业务校验**（预算偏差 >20%、天数一致性、空活动日）。加上 prompt 里的 JSON Schema 强约束 + 主备 LLM 切换。
**引用**：`nodes/validate.py`、`planner_prompt.py`、`nodes/planner.py`

### Q7：Prompt 怎么保证约束一定被遵守？

在 `planner_prompt.py` 里写**约束必含关键词强制规则**：用户消息含"清真"→ tips 必含"清真"；含"雨天"→ warnings 必含"室内"且禁止"露天"。再配 JSON Schema（`dailyItinerary` 长度=days、budgetBreakdown 5 项非负、禁尾随逗号）。静态前缀稳定放前面、检索数据放末尾，兼顾 Prompt Cache 命中。
**引用**：`services/agent/planner_prompt.py`、`system_prompt.py`

### Q8：流式响应断线怎么办？

SSE 原生 `Last-Event-ID`。服务端每 chunk 带 `id:` 序号并双写 Redis stream；客户端断线自动重连并带 `Last-Event-ID`，服务端从 Redis 找到该 sequence 续推，客户端 SSEParser 按 eventId dedup。边界：工具未跑完等完成再续、sequence gap 校验、IDOR 用 userId 防护。
**引用**：`utils/stream.py`、`trip-front/src/api/stream-parser.ts`

### Q9：怎么评估 Agent / RAG 质量？

三层：检索层 Hit@K/MRR、生成层 Faithfulness/Answer Relevancy（LLM-as-Judge，temp=0）、线上层点赞率/高分低满意度。10 个 YAML fixture + domain/general/multi_turn/ragas 四类评估器，支持 mock/真实/CI 多模式；线上反馈可一键转 fixture 形成闭环。
**引用**：`eval/`、`eval/evaluators/`、`eval/retrieval/`

### Q10：你的多 Agent 是怎么设计的？

**如实讲**：当前是**单 Agent + LangGraph 双图工作流**（ChatGraph 路由 + PlannerGraph 规划），不是多自主 Agent 协作。我做过完整多 Agent 演进设计（Orchestrator + Planner/Recommender/Chat/Budget 四 Specialist，共享 AgentState），核心判断是：C 端旅行场景需要确定性、可追踪，所以选 Supervisor 而非 Swarm；且早期单 Agent 更务实，当需要处理"规划+预算"复合意图、频繁加能力时多 Agent 收益才覆盖编排复杂度。
**引用**：`docs/多_agent_架构设计_2026-07-04_00-26.md`、`chat_graph.py`、`planner_graph.py`

### Q11：MCP 是什么，你怎么用的？

MCP（Model Context Protocol）是统一 Agent 接工具/数据源的标准协议，把 N×M 集成变成 N+M。我用 `asyncio.subprocess` 拉起 Node 版高德 MCP server，走 **stdio JSON-RPC**（`tools/list` / `tools/call`），自研客户端带熔断/限流/缓存，再用 tool_loader 把 MCP 工具动态转成 LangChain StructuredTool，实现规划时实时查高德全库 POI。
**引用**：`services/mcp/amap_client.py`、`services/mcp/tool_loader.py`

### Q12：工程规范做了什么？

structlog JSON 日志 + 敏感字段脱敏 + request_id 全链路；全局异常处理器（AppException/IntegrityError→409/JWT→401/兜底）；中间件（限流 + 幂等 + CORS + GZip）；GitHub Actions CI（后端 ruff+mypy+pytest，前端 prettier+build+vitest）；token 预算守卫 + 并发守卫 + 工具/LLM 缓存。
**引用**：`utils/logger.py`、`middleware/`、`.github/workflows/`

---

## Part 4 — Trade-off 论述

### Trade-off 1：为什么 SSE 而不是 WebSocket？

SSE 单向（server → client）本场景足够，且断点续传标准 `Last-Event-ID` 只有 SSE 有；基于 HTTP 长连接，CDN/代理友好，浏览器原生自动重连。WebSocket 双向但握手复杂、移动端兼容差。**何时换**：需要上行高频小消息（<100ms）的双向实时场景。本项目单条消息 5-30s，SSE 完美匹配。

### Trade-off 2：为什么 Chroma 而不是 Milvus？

Chroma 单实例够用（<100K doc）、零配置；Milvus 分布式但重（etcd+MinIO+Pulsar），运维成本高。当前 30,791 POI 用 Chroma（~23 MB）绰绰有余。**何时换 Milvus**：数据 >1M 或需分布式检索 / 高 QPS。

### Trade-off 3：为什么本地关键词改写而不是 LLM 改写？

本地停用词+关键词提取省 ~800ms 且零 LLM 成本，对多数 query 召回已够。**代价**：复杂/口语化 query 改写不如 LLM。目前 `rewrite_query_with_llm` 是预留 TODO，计划用评估驱动 A/B（本地 vs LLM 改写的 Hit@K）再决定是否切换。

### Trade-off 4：为什么单 Agent 双图而不是多 Agent？

早期单 Agent 双图链路短、好调试、无调度税；多 Agent 每请求多一次 Orchestrator LLM 调用（+200-500ms）、状态同步复杂、多跳难排查。**何时升级**：需处理复合意图、多团队并行迭代、频繁加能力（预算/多语言/实时信息）时，多 Agent 的解耦复用收益才覆盖成本。这是"架构复杂度 vs 业务复杂度"的取舍，不存在绝对好坏。

### Trade-off 5：为什么多 Provider 主备而不是单 Provider？

DeepSeek 性价比最高作主；但上游有容量上限（高并发会失败），所以配 Kimi/Agnes 作备，主 LLM 抛错自动 fallback，提升可用性。**代价**：多 Provider 增加配置与 prompt 适配成本（不同 cache 行为需双字段兼容 `prompt_tokens_details.cached_tokens` / `prompt_cache_hit_tokens`）。
**引用**：`config/llm.py`、`nodes/planner.py`

---

## 附录

### 关键代码路径索引
- LLM 主备：`trip-backend/src/config/llm.py`
- 提示词：`services/agent/system_prompt.py`、`planner_prompt.py`
- 工具/MCP：`services/agent/tools/`、`services/mcp/amap_client.py`
- 编排：`services/agent/chat_graph.py`、`planner_graph.py`、`nodes/`
- RAG：`services/knowledge_service.py`、`rag/`（rrf/reranker/embeddings/chroma_client/query_rewriter）
- 记忆：`services/conversation_service.py`、`agent_engine.py`
- 流式：`utils/stream.py`、`trip-front/src/api/stream-parser.ts`
- 评估：`eval/`、`eval/evaluators/`、`eval/retrieval/`
- 工程：`utils/logger.py`、`middleware/`、`.github/workflows/`

### 配套文档
- `docs/agent-interview-gap-analysis.md`：岗位差距分析 + 补强路线图
- `docs/多_agent_架构设计_2026-07-04_00-26.md`：多 Agent 演进方案
