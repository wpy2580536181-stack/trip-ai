# Agent 岗位面试准备：岗位要求梳理 + 项目差距分析 + 补充建议

> 产出日期：2026-07-14
> 适用岗位：AI Agent 开发工程师 / LLM 应用工程师 / RAG 系统工程师
> 配套阅读：`README.md`（项目现状，准确）、`docs/多_agent_架构设计_2026-07-04_00-26.md`（多 Agent 方案）、`docs/interview-guide.md`（⚠️ 已过时，见 §0）

---

## 0. 先修项：你的面试材料与代码存在不一致（最高优先级的雷点）

在讲差距前，必须先指出一个会**直接被面试官抓住**的问题：

你 `docs/` 下的 `interview-guide.md`（自称 Week 4 交付）描述的是**旧版技术栈**，与当前实际代码（`README.md` + `trip-backend/src/`）严重不符：

| 维度 | `interview-guide.md`（旧版叙事） | 当前代码实际（`README.md` + 探索结论） | 风险 |
|---|---|---|---|
| 后端框架 | Express 5 + Prisma + Pino（Node/TS） | **FastAPI + SQLAlchemy(async) + structlog**（Python） | 🔴 技术栈讲错 |
| Agent 框架 | "LangChain-based Agent"（Node 版） | **LangChain + LangGraph（StateGraph）** | 🔴 框架讲错 |
| 模型 | `deepseek-v4-flash` | `deepseek-chat`（主）+ Kimi/Agnes（备，主备切换） | 🟡 模型名错 |
| 数据规模 | "5 城市 1000+ POI" | **30,791 POI / 153 城** | 🔴 数字严重缩水 |
| 工具 | getWeather/getDistance/searchHotels/searchPOI（4 个） | retrieve_knowledge / calculate_distance / search_hotels + **高德 MCP** | 🟡 工具清单不符 |
| 编排 | 未提工作流/LangGraph | **ChatGraph + PlannerGraph 双状态图** | 🟡 漏讲核心架构 |
| 内部矛盾 | Q10 说"LangGraph 重构 ROI 低，单 Agent 够用" | 同目录 `multi-agent-architecture.md` 又设计了完整多 Agent | 🔴 自相矛盾 |

**建议**：面试前必须以 `README.md` + 当前代码为准，**重写 `interview-guide.md`**，删除 Node/Express 叙事，统一为 FastAPI/LangChain/LangGraph 版本，并让所有数字、工具名、架构与代码一致。本文 §5 的"答题映射表"可直接作为重写骨架。

---

## 1. 大厂 Agent 岗位技术要求梳理

### 1.1 八大核心考核维度（横向通用）

| # | 维度 | 面试官期待你讲清的 | 典型追问 |
|---|---|---|---|
| 1 | **LLM 调用与微调** | API 接入、多 Provider 路由、流式、微调/RL 原理 | SFT 时 mask 哪些 token？Agentic RL 奖励怎么设计？ |
| 2 | **Prompt Engineering** | 系统提示、结构化输出、约束跟随、Few-shot、Prompt Cache | 怎么保证 JSON 必含某关键词？长 prompt 怎么省 token？ |
| 3 | **Tool Use / Function Calling** | 工具定义 schema、参数校验、失败重试/降级、错误回灌 | tool_response 用 user 还是 assistant 角色回传？为什么？ |
| 4 | **多 Agent 协调与编排** | Workflow vs Agent 选型、Supervisor/辩论/共享状态、通信 | 你的多 Agent 怎么避免循环/冲突？何时不该用多 Agent？ |
| 5 | **RAG** | 混合检索、查询改写、重排、分块、幻觉缓解 | 怎么做增量索引？召回不准怎么提精度？ |
| 6 | **记忆机制** | 短期上下文 / 工作记忆 / 长期向量记忆分层 | 上下文满了怎么压缩？长期记忆怎么去重/时效？ |
| 7 | **规划与推理** | ReAct / Plan-and-Execute / CoT / ToT / Reflection | 显式规划 vs 隐式规划怎么取舍？长任务怎么反思？ |
| 8 | **向量数据库 + 流式** | 选型（Chroma/Milvus/pgvector）、SSE/流式续传、成本 | Chroma 何时换 Milvus？SSE 断线怎么续？ |

**共识性加分项（四家都看）**：评估体系（任务成功率/步数效率/工具准确率/成本）、可观测性（LangSmith/Langfuse 风格 trace）、安全与成本控制、CI/工程规范。

### 1.2 四家风格差异（针对性备考）

- **字节跳动 — 抠工程实现细节**
  - 不会问"Agent 是什么"，直接问 ReAct 循环里**消息格式怎么设计**（tool_response 必须用 `user` 角色回传，因为那是外部系统返回，不是模型生成的；放 `assistant` 会让模型误以为自己说了这些话）。
  - 高频考 **Agentic CPT→SFT→RL 三阶段**；追问 SFT 时**为什么 mask 掉 observation tokens**（避免模型学习"模仿工具返回"）。
  - 区分"背概念 vs 真做过"的关键：**异常处理与日志追踪**——能否讲清每一步输入/工具/输出/耗时。
  - 参考：你的项目已有自研 Agent trace（`/api/admin/agent-trace`）+ 脱敏 structlog，正好对应。

- **腾讯 — 协议与生态理解**
  - 必问 **Workflow 与 Agent 的区别与选型**（你已有现成 trade-off 论述，见 §4.4）。
  - **MCP 协议原理与应用**（你的高德 MCP 自研 JSON-RPC 客户端是强项）、**A2A 协议与 MCP 的关系**（Google/字节/阿里都考）。
  - Skills 与 Prompt 的区别、Function Call / MCP / Skills 三者关系。

- **阿里巴巴 — 系统设计 + 多 Agent 协作架构**
  - 高频系统设计题："设计支持日均 100 万查询的企业级 RAG 系统""长对话 Memory 怎么优化"。
  - 多 Agent 协作架构：流水线式 / 辩论式 / 共享状态式，讲清"分配 / 避免循环 / 聚合"。

- **百度（文心一言团队）— LLM 原理深度 + 工程分层**
  - 一面偏八股：Transformer 注意力、RoPE/ALiBi 位置编码、RLHF（PPO 原理、DPO vs PPO）、超长上下文（KIMI 窗口扩展）。
  - 工程偏好：**百万级工具系统分层**——Tool Discovery（向量索引/HNSW 加速最近邻）→ Tool Adapter（SchemaValidator + ResultFormatter）→ Execution Control；工具调用**预测缓存**（Tool Call Prediction Cache）。
  - Agent 系统设计：多轮对话管理、工具调用优化、异常处理。

---

## 2. 你项目现状能力盘点（基于当前代码）

| 维度 | 现状 | 证据（绝对路径） | 评级 |
|---|---|---|---|
| LLM 调用 | 多 Provider（DeepSeek 主 + Kimi/Agnes 备）+ 主备切换 + `streaming=True` + token 用量回传 | `trip-backend/src/config/llm.py`、`services/agent/planner.py` | ✅ 强 |
| Prompt | 系统提示 + 结构化 JSON Schema + 约束跟随（清真/雨天必含关键词）+ Prompt Cache 友好前缀 | `services/agent/system_prompt.py`、`planner_prompt.py` | ✅ 强 |
| Tool Use | LangChain `@tool` + 高德 **MCP（自研 stdio JSON-RPC 客户端，含熔断/限流/缓存）** + ReAct `AgentExecutor` | `services/agent/tools/`、`services/mcp/amap_client.py`、`nodes/legacy_agent.py` | ✅ 强 |
| RAG | BGE 向量 + MySQL 关键词 + 评分 **三路召回** + **RRF 融合** + **Cross-Encoder 重排** + 本地 query 改写 | `services/knowledge_service.py`、`rag/rrf.py`、`rag/reranker.py` | ✅ 极强 |
| 向量库 | ChromaDB（HTTP 客户端，cosine） | `rag/chroma_client.py` | ✅ 合格 |
| 流式 | SSE + **Redis 断点续传（Last-Event-ID）** + IDOR 防护 | `utils/stream.py`、`trip-front/src/api/stream-parser.ts` | ✅ 强 |
| 编排 | **LangGraph 状态机**（ChatGraph/PlannerGraph）+ 输出三级自愈（JSON 修复→Schema→业务校验→retry） | `services/agent/*_graph.py`、`nodes/validate.py` | ✅ 强（但非多体） |
| 评估 | **三层 RAG 评估**：Hit@K/MRR + Faithfulness/Relevancy（LLM-as-Judge）+ 线上反馈；13+3 评估器 + YAML fixtures | `eval/`、`eval/evaluators/` | ✅ 强 |
| 工程 | 脱敏 structlog + request_id 全链路、全局异常/限流/幂等、GitHub Actions CI | `utils/logger.py`、`middleware/`、`*.github/workflows/` | ✅ 强 |
| 记忆 | **会话级**摘要 + 对话脉络 + 用户画像（DB 字段注入 prompt） | `services/conversation_service.py`、`agent_engine.py` | ⚠️ 偏弱 |
| 多 Agent | **单 Agent + 节点工作流**，非多体协作/辩论 | `chat_graph.py`、`planner_graph.py` | ❌ 缺失 |
| 规划/推理 | 单次生成 + 校验重试；ReAct 仅 legacy_agent；**无显式 CoT/ToT/Reflection** | `nodes/planner.py`、`nodes/legacy_agent.py` | ❌ 缺失 |
| 微调 | **完全未涉及**（仅调用 API） | — | ❌ 缺失 |
| 路由 | **启发式**（关键词+正则）判断 planning vs general | `nodes/router.py` | ⚠️ 偏弱 |
| Query 改写 | `rewrite_query_with_llm` 仍是 **TODO**，降级本地 | `rag/query_rewriter.py` | ⚠️ 未完成 |

> 结论：你的项目在 **RAG / Tool Use / 流式 / Prompt / 工程规范** 维度已经具备大厂面试级深度；**最大短板是多 Agent 协作、显式推理框架、长期记忆、微调原理** 这四块。

---

## 3. 差距分析（逐一对照岗位要求）

| 岗位维度 | 要求 | 你现有 | 差距 | 风险 |
|---|---|---|---|---|
| 多 Agent 协调 | 能讲 Supervisor/辩论/共享状态，会做选型 trade-off | 单 Agent 工作流 | **无多体协作实现**，只能讲"设计过" | 🔴 高（字节/阿里高频） |
| 规划与推理 | ReAct/Plan-and-Execute/CoT/ToT/Reflection | 单次生成+重试 | 无显式思维链/反思 | 🔴 高 |
| 记忆机制 | 短/工作/长期三层，长期向量库 | 会话级摘要+画像 | 无跨会话长期向量记忆 | 🟡 中 |
| LLM 微调 | 懂 SFT/RL、能讲 mask observation、最好做过 | 仅 API 调用 | 原理可能答、实践 0 | 🟡 中（百度重） |
| 路由 | LLM 语义路由 / Tool RAG | 关键词正则 | 工具多了会失准 | 🟡 中 |
| Query 改写 | LLM 改写提升召回 | 本地降级 | 有 TODO 未落地 | 🟡 低-中 |
| RAG | 混合检索/重写/重排/增量 | 已很强 | 增量索引未做 | 🟢 低 |
| 评估 | Agent 端到端（成功率/步数/工具准确率/成本） | 仅 RAG 评估 | 缺 Agent 级指标 | 🟡 中 |
| 文档一致性 | 讲的和代码一致 | 旧版文档冲突 | 雷点 | 🔴 高（§0） |

---

## 4. 补充建议（可落地、可演示、按 ROI 排序）

### P0 — 必做，低成本高回报

**4.1 刷新并统一面试叙事（消除 §0 雷点）**
- 动作：以 `README.md` + 当前代码为准重写 `interview-guide.md`；删除所有 Express/Prisma/5城市 叙事；用 §5 映射表作骨架。
- 演示性：100%（面试第一关就是"讲清项目"）。

**4.2 路由升级为 LLM 语义路由 / Tool RAG**
- 现状：`nodes/router.py` 是关键词+正则。
- 落地：用**小模型做意图分类**（复用现有 fallback 小模型），或当工具数 > 10 时引入 **Tool RAG**（对工具描述做向量检索，只把 top-k 塞进 context）。
- 面试怎么讲："早期用启发式路由够用；当工具规模到几十个，关键词路由会失准，所以我引入了语义路由/Tool RAG，工具选择准确率从 X 提升到 Y。"
- 演示性：高（直接对标百度"百万级工具分层"考点）。

**4.3 落地 `rewrite_query_with_llm`（填 TODO）**
- 现状：`rag/query_rewriter.py` 的 LLM 改写是 TODO，降级本地。
- 落地：用 LLM 做 query 改写（扩展同义、拆解复合意图），并**跑 A/B 对比**本地改写 vs LLM 改写的 Hit@K（复用你已有的检索评估 `eval.retrieval.run`）。
- 面试怎么讲：拿真实数据对比"本地改写 Hit@5=0.82 vs LLM 改写 Hit@5=0.89"，体现用评估驱动优化。
- 演示性：高（量化数字 + 复用现有评估体系）。

### P1 — 核心加分，对应最大差距

**4.4 多 Agent 落地（用你已有的设计稿直接实现）**
- 现状：已有 `docs/多_agent_架构设计_2026-07-04_00-26.md` + `multi-agent-architecture.html` 方案（Orchestrator + Planner/Recommender/Chat/Budget）。
- 落地（渐进式，非推倒重来）：
  1. 把 `chatGraph` 升级为 **OrchestratorAgent**（LLM 语义路由替代启发式）；
  2. 把 RAG 管线封装为 **RecommenderAgent**；`plannerGraph` → **PlannerAgent**；`legacy_agent` → **ChatAgent**；新增 **BudgetAgent**（实时预算校验，超支回调度 Planner 重排）；
  3. 用 LangGraph `StateGraph` 共享 `AgentState`（messages/trip_context/plan_draft/poi_candidates）。
- 面试怎么讲（trade-off 金句）："早期单 Agent + 双图架构更务实（链路短、好调试）；当要处理'规划3天+预算5000'这类**复合意图**、且要频繁加能力时，多 Agent 的解耦与复用收益才覆盖得了编排复杂度。我没盲目上 Swarm，因为 C 端需要确定性可追踪。"
- 演示性：**极高**（复合意图一次调度多专家，直接演示；且能讲清"何时不该用多 Agent"——这正是腾讯/阿里高频考点）。

**4.5 显式推理与 Reflection（补规划维度）**
- 落地：在 `planner` 节点引入 **Plan-and-Execute**：先让 LLM 输出思考链/计划（显式 CoT），再执行；新增 **ReviewerAgent/Reflection 节点**对生成行程做自我批判（预算偏差、天数一致性、空活动日），不达标则重排。
- 也可做 **Agentic RAG**：检索成为 agent 可多轮调用的子步骤（plan→retrieve→reflect→再 retrieve）。
- 面试怎么讲："我用 Plan-and-Execute 替代纯单次生成，让规划可审计；Reflection 节点把'行程质量自检'从被动校验升级为主动改进，行程一次通过率从 X 提升到 Y。"
- 演示性：高（可直接对比有无 Reflection 的行程质量）。

**4.6 长期记忆（Mem0 风格用户向量画像）**
- 现状：仅会话级摘要 + DB 用户画像字段。
- 落地：引入**长期语义记忆层**——把用户偏好/历史行程向量化存入 Chroma（独立 collection），跨会话检索注入；实现"重要性加权 + 时间戳过滤 + 定期清理"去重。
- 面试怎么讲："短期记忆=对话窗口+摘要压缩；长期记忆=用户向量库外挂检索，本质是把'用户习惯'持久化，二次来访能直接复用。"
- 演示性：中-高（"老用户第二次来，Agent 自动记得偏好"是很直观的 demo）。

### P2 — 差异化亮点，针对微调考点

**4.7 微调原理 + 最小实验（覆盖 LLM 微调维度）**
- 不一定要真上生产微调，但要能讲清且最好做过一次：
  - **原理级**：准备"Agentic 训练三阶段"话术——CPT（注入领域/工具知识）→ SFT（构造 Thought-Action-Observation 轨迹，**mask 掉 observation tokens** 避免模型学"模仿工具返回"）→ RL（奖励=任务成功率-格式惩罚，用 DPO/PPO）。
  - **最小实验**：在开源小模型（如 Qwen2.5-0.5B/3B）上用 **LoRA 做一次 function-calling 微调的 toy 训练**，产出"数据构造→训练→评测" pipeline 并写进文档；或接入**百度千帆/阿里百炼**平台做一次可视化微调 demo。
  - 工程衔接：在 Agent 里预留"意图分类/工具选择可切换到微调小模型"的开关，呼应你的多 Provider 架构。
- 面试怎么讲（百度向）："虽然生产用 API，但我理解并实践过 function-call 微调——SFT 时 observation 要 mask，否则模型会过拟合工具返回格式……"
- 演示性：中（原理可讲，实验可展示训练曲线/评测对比）。

**4.8 Agent 端到端评估补全**
- 现状：RAG 评估强，但缺 Agent 级指标。
- 落地：在 `eval/` 增加**任务成功率 / 平均步数 / 工具调用准确率 / Token 成本**四类指标（复用现有 fixture + LLM-as-Judge），输出"带成本的任务完成率"报告。
- 面试怎么讲："我不只评估 RAG 召回，更评估 Agent 端到端——用真实 fixture 跑出'任务成功率 92%、平均 4.2 步、工具准确率 96%、单次成本 ¥0.0X'，证明 Agent 比人工/基线更省。"
- 演示性：高（量化 + 复用已有评估框架，几乎零新基础设施）。

---

## 5. 面试答题映射表（每个维度 → 你项目里的故事）

| 维度 | 一句话故事（基于真实代码） |
|---|---|
| LLM 调用 | "多 Provider 接入，DeepSeek 主 + Kimi/Agnes 备，主 LLM 抛错自动 fallback；SSE 流式且回传 token 用量。" |
| Prompt | "系统提示定义角色+工具规则+约束跟随（清真/雨天必含关键词）；JSON Schema 强约束输出；静态前缀稳定以命中 Prompt Cache。" |
| Tool Use | "两类工具：LangChain `@tool`（带超时重试降级缓存）+ 高德 MCP（自研 stdio JSON-RPC 客户端，含熔断/限流）；legacy_agent 是标准 ReAct，tool 结果以 user 角色回灌。" |
| 多 Agent | "当前是单 Agent + LangGraph 双图工作流；我已设计渐进式多 Agent（Orchestrator+4 Specialist），能讲清何时该上、何时不该上。"（⚠️ 若已落地 4.4，则讲实现） |
| RAG | "三路召回（向量/MySQL关键词/评分）+ RRF 融合 + Cross-Encoder 重排；本地 query 改写省 LLM；30,791 POI/153 城；检索 P50 ~640ms。" |
| 记忆 | "短期=对话窗口+LLM 摘要压缩+token 预算触发 compaction；用户画像从 DB 注入；（4.6 后）长期=用户向量库跨会话检索。" |
| 规划推理 | "PlannerGraph 单次生成+三级自愈（JSON修复→Schema→业务校验→retry）；legacy_agent 走 ReAct；已规划引入 Plan-and-Execute + Reflection（4.5）。" |
| 向量库 | "Chroma 单实例够用（<100K doc）；讲了何时换 Milvus（>1M / 分布式）。" |
| 流式 | "SSE + Redis 断点续传（Last-Event-ID），断线续推不丢不重，节省 ~90% 重复 token；前端 SSEParser 按 eventId dedup。" |
| 评估 | "三层 RAG 评估 + LLM-as-Judge + 线上反馈闭环；13+3 评估器 + YAML fixture；（4.8 后）Agent 端到端指标。" |
| 工程 | "脱敏 structlog 全链路 request_id、全局异常/限流/幂等、GitHub Actions CI、自研 Agent trace 对标 LangSmith。" |

---

## 6. 30 天落地路线图

| 周 | 重点 | 交付物 |
|---|---|---|
| W1 | **P0**：刷新面试叙事（§0/§4.1）+ 路由升级（4.2）+ 填 Query 改写 TODO（4.3） | 新版 `interview-guide.md`、语义路由、LLM 改写 A/B 数据 |
| W2 | **P1**：多 Agent 落地（4.4） | Orchestrator+Specialist 可运行，复合意图 demo |
| W3 | **P1**：显式推理+Reflection（4.5）+ 长期记忆（4.6） | Reflection 节点、用户向量记忆库 |
| W4 | **P2**：微调原理+最小实验（4.7）+ Agent 端到端评估（4.8） | 微调 toy pipeline / 平台 demo + Agent 评估报表 |

> 优先级建议：先把 §0 雷点和 P0 做完（1 周），这是面试"不翻车"的底线；P1 是拉开差距的关键；P2 是差异化亮点，时间不够可先准备原理话术。

---

## 附录

### A. 关键代码路径索引（讲项目时随手可指）
- LLM 配置/主备：`trip-backend/src/config/llm.py`
- 系统/规划提示词：`trip-backend/src/services/agent/system_prompt.py`、`planner_prompt.py`
- 工具：`trip-backend/src/services/agent/tools/`、`services/mcp/amap_client.py`
- 编排：`trip-backend/src/services/agent/chat_graph.py`、`planner_graph.py`、`nodes/`
- RAG：`trip-backend/src/services/knowledge_service.py`、`rag/`（rrf/reranker/embeddings/chroma_client/query_rewriter）
- 记忆：`trip-backend/src/services/conversation_service.py`、`agent_engine.py`
- 流式：`trip-backend/src/utils/stream.py`、`trip-front/src/api/stream-parser.ts`
- 评估：`trip-backend/eval/`、`eval/evaluators/`、`eval/retrieval/`
- 工程：`utils/logger.py`、`middleware/`、`*.github/workflows/`

### B. 现有可复用资产
- `docs/多_agent_架构设计_2026-07-04_00-26.md` + `multi-agent-architecture.html`：多 Agent 方案（直接用于 4.4）
- `docs/interview-guide.md`：旧版叙事（需重写，见 §0）
- `eval/` 三层评估框架：直接扩展 Agent 端到端指标（4.8）

### C. 参考来源（大厂考点）
- 字节/腾讯/阿里 Agent 面试差异实录（CSDN）
- Agent 开发岗专项面试题库（GitHub AgentGuide）
- 2026 大厂 50 道 AI Agent 高频题（xxmr.cn）
- 百度文心一言 Agent 岗面试全解析（cloud.baidu.com）
- Nowcoder Agent 面经汇总
