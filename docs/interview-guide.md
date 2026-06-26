# 项目讲解文档（Interview Guide）

> Week 4 交付（2026-07-22）
> 配套 `docs/interview-plan.md` 亮点 4
> 候选人目标：1.5-2 小时讲完整个项目

## 目录

- [Part 1 — 项目总览](#part-1--项目总览)（5 分钟）
- [Part 2 — 4 个亮点 STAR](#part-2--4-个亮点-star)（30 分钟）
- [Part 3 — 10 个高频问题预演答案](#part-3--10-个高频问题预演答案)（30 分钟）
- [Part 4 — Trade-off 论述](#part-4--trade-off-论述)（10 分钟）

---

## Part 1 — 项目总览

### 一句话定位

**trip-ai 是一个 AI 旅行规划助手**：用户说一句"想去北京玩 3 天预算 5000"，Agent 自动调用工具链（天气/距离/酒店/POI 检索）生成结构化行程，所有 chat 用 SSE 流式输出 + 断点续传。

### 技术栈一览

| 层 | 选型 | 备注 |
|---|---|---|
| 前端 | Vue 3 + Vite + Pinia + Element Plus | 8800 行代码（5720 TS + 3055 Vue） |
| 后端 | Express 5 + Prisma + Pino | LangChain-based Agent |
| 数据库 | MySQL 8（Prisma ORM） + Redis 7 + Chroma | Chroma 存 5 城市 1000+ POI |
| LLM | DeepSeek deepseek-v4-flash | temperature 0.7 / maxTokens 8000 |
| Embedding | bge-small-zh | 384 维 |
| 部署 | Docker Compose | MySQL/Chroma/Redis 3 容器 |

### 4 个核心能力

1. **AI Agent**：4 工具链（天气/距离/酒店/POI）+ function calling
2. **RAG**：Chroma 向量检索 + 知识库增强 prompt
3. **流式 chat**：SSE + Last-Event-ID 断点续传
4. **评估体系**：10 fixture + 13 evaluator + mock/真实/CI/多采样

### 4 周亮点的预告

接下来 30 分钟重点讲 4 个亮点（4 周前没有的）：

- **断点续传流式 Agent**（Week 1）—— 解决"流到一半断了重传浪费 token"
- **可视化 Agent 调试**（Week 2）—— 类似 LangSmith 的生产级工具
- **反馈→fixture 自动化闭环**（穿插）—— 用户 👍/👎 直接转评估用例
- **生产压测报告**（Week 3）—— 5 个量化数字 + 6 张图表

### 数据 / 规模

| 指标 | 数值 |
|---|---|
| 代码量 | 8800 行（5720 TS + 3055 Vue） |
| 测试 | 9 passed / 6 failed（pre-existing）/ 56 eval 测试 |
| Fixture | 10 个 + 实战 fixture 1 个 |
| Evaluator | 13 个（含 3 冲突分支） |
| 文档 | 17 篇（亮点 4 篇 + 主题 13 篇） |
| 历史 QPS | 6.67（10 并发） |
| SSE P99 | 47.0s（10 并发） |
| Cache 命中率 | 40.2% |
| LLM /recommend P50 | 29.1s |
| 单流 chunk 数 | 1000+ |

---

## Part 2 — 4 个亮点 STAR

### 亮点 1：断点续传流式 Agent

**S**ituation（业务痛点）
用户在流式收 AI 回复到一半时（网络断/刷新/切后台）会丢失所有已收内容，整段重传浪费 token 和等待时间。

**T**ask（我的目标）
设计带断点续传的流式 Agent。客户端断线后能精确从断点续传，不丢 chunk、不重复 chunk。

**A**ction（技术方案 + 3 个关键决策）
1. **客户端用 EventSource**（SSE 原生自动重连 + `Last-Event-ID` 头），放弃 fetch 循环
2. **服务端给每个 chunk 加 `id:` 字段**（SSE 标准），重连时浏览器自动带 `Last-Event-ID`
3. **Redis streamStore 持久化 sequence**（commit `b853530`），重启不丢；`ResumableStream` helper（`d9e82f9`）

**3 个边界处理**：
- agent 中断时工具还在跑 → 服务端等工具完成后才续推
- 重复 chunk → 客户端 `SSEParser` 按 `eventId` dedup（`7d5d72d`）
- sequence gap → 字节级校验（`streamable-agent-resumable.md`）

**R**esult（量化结果）
- 续传延迟 < 100ms（Redis 命中）
- 节省 ~90% 重复 token（不再整段重传）
- 测试：后端 103/103 + 前端 19/19 SSEParser 全过

详细：`docs/streamable-agent-resumable.md`

---

### 亮点 2：可视化 Agent 调试

**S**ituation
Agent 内部状态不可见。线上出 bug 时定位靠 `grep` 日志，看不到"agent 调了哪些 tool、参数是什么、返回是什么、每步耗时"。

**T**ask
做类似 LangSmith 的生产级调试工具：admin 能在浏览器回放任意一次 agent 决策。

**A**ction
1. **Prisma AgentStep 表**（`96d2762`）：`messageId + step + type + name/args/output/durationMs`，`@@index` + `onDelete Cascade`
2. **TraceRecorder**（`e6ab94e`）：buffer + flush，flush 失败只 warn 不抛
3. **agentEngine 集成**（`f2bfb6b`）：`on_tool_start` / `on_tool_end` / `complete` / `error` 4 钩子
4. **admin 鉴权三层**（路由 meta + `req.user.roleId` + 前端 `beforeEach`）
5. **关键 fix**（`fc104d0`）：tripService 预创建空 assistant message，agentEngine 拿到真实 messageId（避免 TraceRecorder 用 `messageId=0` FK 失败被 warn 吞）

**R**esult
- 1 次 chat 看到 5-10 个 step（含 4 tool 调用 + 1 complete）
- 字段 200+ 字符 JSON 用 van-collapse 折叠
- AdminTrace.vue 时间轴 + `GET /api/admin/agent-trace/:messageId`（admin 守卫）
- Dashboard "🔍 Trace" 按钮直接跳到该 message 的 trace 页

详细：`docs/agent-trace.md`

---

### 亮点 3：反馈→fixture 自动化闭环

**S**ituation
评估 fixture 不会自动进化。线上用户的 👍/👎 反馈被记录但没回流到评估系统，人工维护 fixture 永远追不上真实问题。

**T**ask
用户 admin 点 "📋 转 fixture" 按钮，一键把失败案例变成评估 fixture，下次 eval 自动覆盖。

**A**ction
1. **fixtureConverter 纯函数**（`63549dc`，15 测试）：feedback → YAML fixture skeleton
2. **feedbackService 3 冲突分支**（commit `ccf8382`）：文件存在追加 `-1`/`-2`、版本升级、纯跳过
3. **API + 前端**：`POST /api/feedback/admin/convert-to-fixture`（admin 守卫 1-50 ids）+ Dashboard "📋 转 fixture" 按钮
4. **CLI**：`pnpm feedback:to-fixture --feedback-id=N | --days=7 | --dry-run`
5. **Runner 扫 `fixtures/**/*.yaml`** 双目录（`fixtures/` + `fixtures/generated/`）

**R**esult
- 1 次点击转 fixture（5 步 modal 流程）
- 3 冲突处理（重复/版本/手动）单测覆盖
- 实战 fixture：`1-eval-test-北京-2-天简单行程.yaml`（`must_contain_keywords=[北京]` + `must_not=[上海/广州/深圳]`）

详细：`docs/feedback-to-fixture.md`

---

### 亮点 4：生产压测报告

**S**ituation
服务能扛多少 QPS？token 节省多少？缓存命中率？—— 不知道。面试时被问"性能数据"只能猜。

**T**ask
真实跑压测，量化系统能力，输出 5 数字 + 1 报告 + 1 README 章节。

**A**ction
4 场景压测 + 6 张图表：
1. **HTTP**（`e45b1cb`）：autocannon 登录 + 历史 30 秒
2. **SSE**（`fe31c58`）：4 并发级别 × 20 流（自定义 fetch reader 处理 SSE）
3. **LLM**（`482a761`）：10 个不同 city/days/budgets 顺序调
4. **Cache**（`e4c65ba`）：49 个相似请求测 prompt cache 命中率
5. **图表**（`ede9085`）：chartjs-node-canvas 生成 6 张 PNG

**R**esult（5 关键数字）

| 指标 | 数值 | 条件 |
|---|---|---|
| 历史 QPS | **6.67** | 10 并发 |
| SSE P99 (10 并发) | **47.0s** | 含真实 LLM + 60% cache 命中 |
| Cache 命中率 | **40.2%** | 49 相似请求 |
| LLM /recommend P50 | **29.1s** | 10 个不同请求 |
| 单流 chunk 数 | **1000+** | 8-50 段 itinerary |

**3 关键发现**：
1. **DeepSeek 上游是容量上限**（conc=20 全失败）
2. **Chroma 检索占 60% 延迟**（Redis 缓存 ROI 最高）
3. **生产 rate limit 工作正常**（登录 20/min/user 是预期）

详细：`docs/performance-benchmark.md`

---

## Part 3 — 10 个高频问题预演答案

### Q1：介绍一下你的项目？

**答案（150 字）**：
trip-ai 是 AI 旅行规划助手。核心是 LangChain-based Agent + RAG + 流式 chat。8800 行 TS+Vue，56 测试。架构 3 层：Vue 3 前端 / Express 5 后端 / MySQL+Redis+Chroma+DeepSeek。4 周前我加 4 个亮点：断点续传流式 Agent（解决"流到一半断了重传浪费"）、可视化 Agent trace（类似 LangSmith）、反馈→fixture 自动化闭环（用户 👍/👎 直接转评估）、生产压测（5 数字 + 6 图表）。技术上 LangChain function calling、Chroma 向量检索、Prisma ORM、Pino 结构化日志全栈式推进。

**引用**：`README.md`、`docs/interview-plan.md`、`docs/performance-benchmark.md`

---

### Q2：RAG 链路里你做了什么优化？

**答案（180 字）**：
链路是 query → bge-small-zh embedding → Chroma 向量检索（top-K=5）→ 重排序 → prompt 增强。3 优化点：(1) Chroma 选型：单实例够用（< 100K doc），未来数据 > 1M 再换 Milvus；(2) 知识库从 5 城市 1000+ POI 起步，结构化字段（价格/距离/评分）让 LLM 知道真实距离；(3) 检索后做 context stuffing 注入 system prompt，让 LLM 看到真实数据。瓶颈在 Chroma 检索（~60% /recommend 耗时），加 Redis 缓存可减半耗时。

**引用**：`docs/performance-benchmark.md`（瓶颈分析）、`trip-server/src/services/vectorStore.ts`

---

### Q3：Agent 怎么决定调哪个工具？

**答案（180 字）**：
LangChain function calling 让 LLM 自己决定调哪个 tool。当前 4 个 tool：getWeather（天气）、getDistance（距离）、searchHotels（酒店）、searchPOI（POI 检索）。每个 tool 包 Zod schema 做参数校验，LLM 输出不符合 schema 时自动 retry 3 次。3 层重试：单工具失败 → 换工具 → fallback 到默认推荐。`agentEngine.ts:17` 集成 TraceRecorder 记录每步调用。`on_tool_start` / `on_tool_end` 4 钩子写到 AgentStep 表（`f2bfb6b`）。

**引用**：`trip-server/src/services/agent/agentEngine.ts:17,116,129,140`、`docs/agent-trace.md`

---

### Q4：上下文怎么管理不会超 token？

**答案（180 字）**：
3 层防御：(1) **token 阈值**（`HISTORY_MAX_TOKENS=8000`）—— DeepSeek 上限 8K；(2) **分层摘要**—— recent 5 轮全量 + old 摘要；(3) **增量压缩**—— 每 10 轮触发 `compressConversation`。`contextManager.ts:45` 核心实现。压测显示 /recommend 一次 LLM 调用 29s 主要花在 prompt 体积（30-50K tokens）。配置项全部在 `config/llm.ts:8-15`，可热调。

**引用**：`trip-server/src/services/contextManager.ts:45`、`trip-server/src/config/llm.ts`、`docs/context-management-improvements.md`

---

### Q5：LLM 输出不稳定你怎么处理？

**答案（180 字）**：
4 层防御：(1) **Zod schema 强类型校验**—— tool 输入和 /recommend 输出都过 Zod；(2) **JSON 修复器**（`docs/llm-json-robustness.md`）—— 3 次重试，修复常见错（缺逗号/多括号/截断）；(3) **`maxTokens: 8000`**（`config/llm.ts`）—— 防止 JSON 截断（之前 4000 经常截断导致 38s+ 失败，提到 8000 降到 25s，commit `8ed871d`）；(4) **Cache 命中 40%**（DeepSeek prompt cache 自动）—— 减少重试概率。

**引用**：`docs/llm-json-robustness.md`、`trip-server/src/config/llm.ts:8-15`、commit `8ed871d`

---

### Q6：流式响应断线怎么办？

**答案（180 字）**：
SSE 原生 `Last-Event-ID` 头。客户端用 `EventSource`（替代 fetch 循环）自动重连，重连时浏览器自动带 `Last-Event-ID` 头；服务端 `ResumableStream` helper（commit `d9e82f9`）从 Redis streamStore（`b853530`，17 测试）找到该 sequence 续推。客户端 `SSEParser`（`7d5d72d`，19 测试）按 `eventId` dedup 重复 chunk。3 个边界处理：agent 中断时工具还在跑 → 服务端等工具完成；sequence gap → 字节级校验；权限（IDOR）→ userId 校验。

**引用**：`docs/streamable-agent-resumable.md`、`trip-server/src/services/resumableStream.ts`、commits `b853530` / `d9e82f9` / `7d5d72d`

---

### Q7：怎么评估 Agent 质量？

**答案（180 字）**：
4 模式评估体系：(1) **mock LLM** —— CI 跑，5 秒出结果；(2) **真实 LLM 单次** —— 本地调试；(3) **真实 LLM 多采样**（3-5 次取中位数）—— 关键场景；(4) **报告** —— JSON+HTML 自动生成。10 fixture + 13 evaluator：evaluator 类型含 `must_contain_keywords` / `must_not` / `regex` / `json_schema` / `semantic_match`。fixture 用 YAML 描述场景，runner 扫 `fixtures/**/*.yaml` 双目录。反馈→fixture 闭环让 fixture 自动进化。

**引用**：`docs/agent-eval.md`、`docs/feedback-to-fixture.md`、`trip-server/eval/`

---

### Q8：性能瓶颈在哪里？

**答案（180 字）**：
/recommend 接口 4 环节耗时分布（`docs/performance-benchmark.md` 瓶颈分析）：(1) **Chroma 向量检索 ~60%**（~17s）—— 头号瓶颈，加 Redis 缓存 ROI 最高；(2) **DeepSeek LLM 推理 ~30%**（~9s）—— 上游限流，conc=20 全失败；(3) **JSON 解析 + Zod 验证 ~5%**；(4) **DB 写入 ~5%**。HTTP 端 6.67 QPS 受生产 rate limit 保护（登录 20/min/user 正确工作）。SSE 端 P99 47s 含真实 LLM 调用。

**引用**：`docs/performance-benchmark.md` 瓶颈分析表、commit `ede9085`（6 图表）

---

### Q9：安全做过什么？

**答案（180 字）**：
17 项 + 5 项后续加固。核心：(1) **bcrypt 12** 密码哈希（业界标准）；(2) **JWT 128 位** + 24h 过期 + refresh token；(3) **SSRF 防护** —— 工具调用禁止内网 IP；(4) **rate limit** —— 登录 20/min/user，/recommend 5/min/user；(5) **Pino 结构化日志**（13 child logger，commit `5dbd822`）—— `requestId` 全链路追踪；(6) **admin 鉴权三层**（路由 meta + `req.user.roleId` + 前端 `beforeEach`）。

**引用**：`docs/pino-logging.md`、`docs/llm-rate-limiting.md`、commit `5dbd822`（Pino 改造）、commit `ffc72d7`（路由守卫修复）

---

### Q10：接下来会怎么改进？

**答案（180 字）**：
3 优先级（按 ROI）：(1) **Redis POI 缓存**（高 ROI）—— /recommend 耗时减半，从 29s → 15s；(2) **多 LLM provider 路由**（中 ROI）—— 加 Kimi 备用，解决 conc>10 时的上游限流；(3) **LangGraph 重构**（低 ROI）—— 多 Agent 编排（行程规划 + 攻略 + 预算分离），但当前单 Agent 够用，边际收益递减。短期还会做：CI 完整化（GitHub Actions + eval）、OTel traceId 接入、`test-alert` prod gate。

**引用**：`docs/performance-benchmark.md` 后续优化表、`docs/superpowers/specs/`

---

## Part 4 — Trade-off 论述

### Trade-off 1：为什么 SSE 而不是 WebSocket？

**论述（150 字）**：
SSE 单向（server → client），本场景就够。WebSocket 双向但握手复杂，移动端兼容性差，断点续传标准（`Last-Event-ID` 头）只有 SSE 有。SSE 基于 HTTP/1.1 长连接，CDN/代理友好。EventSource 浏览器原生支持自动重连（vs WebSocket 需手写）。**何时换 WebSocket**：双向需求（实时聊天输入也上行）+ 高频小消息（< 100ms）。本项目 5-30s/消息，SSE 完美匹配。

---

### Trade-off 2：为什么 Chroma 而不是 Milvus？

**论述（150 字）**：
Chroma 单机够用（< 100K doc），零配置；Milvus 分布式但重（etcd + MinIO + Pulsar），M1 Pro 16GB 跑不动。Chroma 嵌入式 API 简单（`chromadb` Python 或 `chromadb` JS）。**QPS 对比**：Chroma 单实例 6.67 QPS / 60% 延迟；Milvus 分布式可上千 QPS 但运维成本 5x。**何时换 Milvus**：数据 > 1M doc 或需要分布式检索。本项目 5 城市 1000+ POI，Chroma 完美。

---

### Trade-off 3：为什么 Redis 缓存 + 内存缓存双层？

**论述（150 字）**：
Redis 持久化跨重启，内存快但重启清零。分工：(1) **必须 Redis** —— `streamStore`（断点续传不能丢）、feedback stats、rate limit counter；(2) **可内存** —— `tokenUsageLog`（`docs/online-feedback.md` 标注 v2 切 Redis）、`LLM_TOKEN_BUDGET`（50000/h/user 重启清零可接受）、feedback 短期缓存。**优势**：Redis 写压力减半（每分钟少 100+ 次），`pnpm test` 跑得快（无 Redis 依赖）。

---

### Trade-off 4：为什么 in-memory token budget 而不是持久化？

**论述（130 字）**：
MVP 阶段单实例够用。持久化会增加 DB 写入压力（每分钟 100+ 次）和一致性复杂度（多实例需 Redis 原子计数）。v2 切 Redis hash counter：`INCRBY token_budget:{userId} {tokens}` + `EXPIRE 3600`。**单实例 vs 多实例的临界点**：QPS > 50 或实例数 > 3。当前 6.67 QPS / 单实例，in-memory 0 风险。`trip-server/src/services/llmGuard/tokenBudget.ts`。

---

### Trade-off 5：为什么单 LLM provider 而不是多 provider 路由？

**论述（150 字）**：
DeepSeek 性价比最高（输入 ¥1/M tokens，输出 ¥2/M）。压测显示 conc=20 全失败，但本项目真实并发 < 5（`docs/performance-benchmark.md` 场景 2）。多 provider 增加维护成本：不同 SDK（DeepSeek 兼容 OpenAI）/ 不同 prompt 优化（GPT-4 中文差）/ 不同 cache 行为（DeepSeek prompt cache 字段双 fallback `prompt_tokens_details.cached_tokens` 新 vs `prompt_cache_hit_tokens` 旧）。**何时多 provider**：日活 > 1K 或 SLA 要求 99.9%。

---

## 附录

### 引用资源

- 4 周亮点详细文档：
  - `docs/streamable-agent-resumable.md`（断点续传）
  - `docs/agent-trace.md`（可视化 trace）
  - `docs/feedback-to-fixture.md`（反馈→fixture）
  - `docs/performance-benchmark.md`（压测）
- 项目计划：`docs/interview-plan.md`
- 主题文档：`docs/agent-eval.md` / `docs/pino-logging.md` / `docs/llm-rate-limiting.md` / `docs/llm-json-robustness.md` / `docs/cache-optimization.md` / `docs/context-management-improvements.md` / `docs/online-feedback.md` / `docs/feedback-dashboard.md` / `docs/alert-system.md` / `docs/RAG_OPTIMIZATION.md` / `docs/agent-improvements.md`
- 架构图：`docs/architecture-diagrams.md`（Mermaid）
- 演示脚本：`docs/demo-script.md`
- 面试 checklist：`tasks/interview-checklist.md`

### 数字索引

5 数字出现位置：
- `README.md`（## Performance 章节）
- `docs/performance-benchmark.md`（主报告）
- `docs/interview-guide.md`（本文档，Part 1 + Part 2 + Q8 + 附录）
