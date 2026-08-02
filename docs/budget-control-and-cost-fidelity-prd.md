# 竞品借鉴改进 PRD：预算控制引擎 + 费用真实性链路

> **文档状态**：已实施（2026-08-01，T1-T9 完成，实施细节见 TDD 与 tasks/budget-control-and-cost-fidelity-plan.md）
> **作者**：AI 助手（基于竞品代码调研 + 本地代码调研）
> **日期**：2026-08-01
> **下游消费者**：开发团队
> **上游输入**：主理人需求「调研 https://github.com/bcefghj/multi-agent-travel-planner，对比产出改进 PRD」+ 双边代码调研报告

---

## 1. 项目信息

| 字段 | 内容 |
|---|---|
| **项目名称** | trip（AI 旅行规划系统，trip-backend + trip-front） |
| **项目类型** | 竞品借鉴 · 能力增强（预算控制 + 费用真实性） |
| **竞品** | [bcefghj/multi-agent-travel-planner](https://github.com/bcefghj/multi-agent-travel-planner)（263★，6 Agent 面试演示项目，Python/Java/Go 三语言，Mock 数据） |
| **原始需求复述** | 调研竞品架构与实现，对比本项目现状，识别可借鉴的改进点，形成 PRD |

---

## 2. 竞品分析

### 2.1 竞品架构摘要

```
用户输入 → PreferenceAgent → DestinationAgent（5维加权评分）
   → [FlightAgent + HotelAgent + ActivityAgent 并行]（asyncio.gather + wait_for + return_exceptions）
   → BudgetAgent（预算校验）──超预算──→ 渐进式降级循环（≤3 轮）
   → COMPLETED / FAILED（8 态显式状态机 PlanningState）
```

### 2.2 双边对比表

| 维度 | 竞品（GitHub） | 本项目（trip） | 差距判断 |
|---|---|---|---|
| **预算控制** | **确定性降级循环**：BudgetAgent 按轮次降级（R1 砍活动 ≤40% → R2 降酒店 ≤35% → R3 换航班 ≤25%），cut_ratio 按超支比例精确计算 | **软约束**：prompt 预算说明 + review 超 15% 打回 → LLM 带 feedback **全量重写**行程，2 轮后放弃（返回带 issue 行程） | 🔴 **最大差距**：打回成本高、结果不可控、无确定性兜底 |
| **费用来源** | Mock 但**费用是一等公民**：数据模型含 price/price_per_night/total_*_cost，按人数/晚数确定性累加 | **费用全部由 LLM 编造**：spots.avg_cost 仅 1.7% 有值且不进上下文；酒店数据无价格；美团 Skill 已有真实价格却未接入生成链路；唯一真实的是交通费粗算 | 🔴 **最大短板**：展示的金额无任何可信度，且无法做真正的预算控制 |
| **打回重试** | 分轮降级、目标明确（每轮改哪一项、砍多少） | 全量重写 2 轮即放弃，feedback 靠 LLM 自行领悟 | 🟡 打回成功率低、token 浪费 |
| **状态机** | 8 态显式 PlanningState，可观测 | 隐式线性流程（orchestrator 代码即状态） | 🟡 进度展示/可观测性弱 |
| **预算分摊公式** | `daily_budget = 预算×0.25/天数/人数`；DestinationAgent 5 维评分（预算30/安全30/季节20/风格15/签证10） | 仅 `hotel_budget = budget/days/1.5` 一处推算 | 🟡 源头分摊缺失，导致生成即超支 |
| **并行容错** | gather + wait_for(30s) + return_exceptions + error_messages 三件套 | Research 阶段 5 工具已并行；variants 串行（有意，LLM 并发受限） | 🟢 差距小，无需改动 |
| **目的地推荐** | 5 维加权评分选 Top3 | 用户直接指定目的地；模糊意图时无候选推荐 | 🟢 定位不同，可选增强 |
| **数据真实性** | Mock（明示可换真实 API） | 真实 RAG + 高德 MCP + 美团 API | 🟢 本项目全面领先 |

### 2.3 结论

竞品的**核心价值 = 确定性预算闭环**（生成后校验 → 确定性地调整 → 收敛）。本项目有更真实的数据底座（RAG/高德/美团）和更丰富的编排（variants/review/意图补全），但**恰恰缺了竞品最强的确定性预算闭环**，且费用本身不可信导致闭环无米下锅。

改进路线 = **先把费用变真（数据链路）→ 再做确定性预算控制（算法）→ 最后优化打回成本（局部重生成）**。

---

## 3. 目标与非目标

### 3.1 ✅ 做（本期范围）

| 优先级 | 模块 | 一句话目标 |
|---|---|---|
| **P0** | 费用真实性链路 | 行程中每项费用有真实来源（RAG avg_cost / 美团价格 / 估算器），且标记来源 |
| **P0** | 预算分解器（Budget Allocator） | 生成前按公式分解预算到各支出项，从源头控制，降低打回率 |
| **P0** | 确定性预算修正器（Budget Corrector） | 超预算时按轮次确定性地生成"目标分配"，替代全量重写 |
| **P1** | 局部重生成 | review 打回时仅重生成问题字段（费用项/活动），不再全量重写 |
| **P1** | 规划状态机显式化 | 显式 8 态 PlanningState，供进度展示与可观测性（与现有 trip-generating-progress 对齐） |

### 3.2 ❌ 不做（明确排除）

| 排除项 | 原因 |
|---|---|
| **并行化 variants**（3 variant 并行执行） | 已在 tech-spec 明确"LLM 并发受限，串行更稳定"，不推翻既有决策 |
| **目的地推荐评分（5 维加权选 Top3）** | 本项目定位用户指定目的地；模糊意图走 intent completion 追问。列为 P2 候选，不在本期 |
| **三语言重写 / 面试资料** | 竞品是面试项目，与本项目定位不同 |
| **接入真实机票/酒店搜索 API（Amadeus 等）** | 已有美团 Skill 覆盖该能力，本期只做链路打通不做新供应商 |
| **LangGraph / CrewAI 框架迁移** | 编排层为纯代码 asyncio，现状良好 |

---

## 4. 现状细节（改动依据）

### 4.1 现有预算链路（全部现状）

```
入口校验（trip_service.py:383，预算 50~1,000,000）
  → prompt 约束（planner_prompt.py:84-135，budgetBreakdown 5 字段规则）
  → 酒店预算推算（research_agent.py:135-137，hotel_budget = budget/days/1.5）
  → review 代码层（review.py:73-89，totalBudget/budget > 1.15 打回）
  → 打回后：feedback 注入 planner_input → PlannerAgent 全量重写（orchestrator.py:175-187）
  → 2 轮重试后放弃，返回带 issues 的行程（orchestrator.py:183-185）
```

**痛点**：
1. 打回依赖 LLM 自行领悟"怎么改"，改完仍可能超支，2 轮即放弃
2. 每次打回全量重写整个行程（含所有天），token 成本高、有引入新幻觉风险
3. 没有按支出项（住宿/餐饮/交通/门票）的分项预算约束，只校验总和

### 4.2 现有费用链路（全部现状）

```
PlannerAgent 生成 budgetBreakdown + 各活动 price  ← LLM 编造（无真实价格数据）
  ├─ spots.avg_cost：30,791 条中仅 532 条有值（1.7%），且 RAG 检索不输出该字段（knowledge_service.py:570）
  ├─ 酒店：data/poi_raw 无价格字段；search_hotels_tool 返回 RAG 文本（无价格）
  ├─ 机票/火车：唯一真实来源 calculate_distance.py cost_min/cost_max 粗算
  └─ 美团 Skill：有真实价格（机票/酒店/火车票/门票）但生成链路未调用
```

**痛点**：金额全部是编的 → 预算控制即使做了，控制的也是假数字。

---

## 5. 需求详述

### 5.1 P0-1 费用真实性链路

**目标**：行程中每项金额具备 `cost_source` 来源标记，优先真实数据，fallback 估算，禁止裸编。

#### 数据层
| 改动 | 内容 |
|---|---|
| `spots.avg_cost` 补全 | 启动 POI ETL 补全流水线（已有 `poi-etl` Skill）：优先高德 POI 价格字段（若有），否则按城市消费水平 × 类别（景点/美食/休闲）估算并标记 `cost_source=estimate` |
| 检索链路暴露价格 | `knowledge_service._rating_search` SELECT 增加 `avg_cost`；`format_search_results` 输出到 LLM 上下文（景点与美食条目各带 avg_cost 字段） |

#### 生成层
| 改动 | 内容 |
|---|---|
| `PlanResult` 增加 `cost_source` | 每个活动项/住宿项增加 `costSource: rag | meituan | estimate | distance` 字段 |
| 估算器 `services/cost_estimator.py`（新） | 确定性估算：住宿（城市档位 × 星级系数）、餐饮（城市档位 × 人均）、门票（avg_cost 缺失时按类别默认值）。城市档位从现有数据推导（参考 `research_bundle_cache` 的 budget 分档思路） |
| 美团价格接入（v1 只读） | `planner_prompt` 中注明：酒店/交通若 Research 阶段通过美团 Skill 查得真实价格（`meituan-travel`），则必须使用该价格并标记 `cost_source=meituan`；查不到时用估算器 |

#### 校验层
| 改动 | 内容 |
|---|---|
| review 新增"来源完整性"软校验 | 无来源标记的费用项 → LLM review warning（不强制打回，P1 再考虑强制） |

**验收标准**：
- [ ] 生成行程中 ≥90% 费用项带 costSource，其中景点门票优先来自 avg_cost（覆盖率从 1.7% 提升至 ≥50%）
- [ ] RAG 检索响应包含 avg_cost 字段（单测断言）
- [ ] 估算器输入输出确定性（同一输入 → 同一输出，单测覆盖）

### 5.2 P0-2 预算分解器（Budget Allocator，源头控制）

**目标**：生成前代码层计算"预算分解目标"，注入 prompt，从源头控制超支。

#### 算法（v1，借鉴竞品占比思路，适配本项目 5 项分解）
```
住宿(accommodation) ≤ budget × 40%
餐饮(food)         ≤ budget × 25%
交通(transportation) ≤ budget × 20%
门票(tickets)      ≤ budget × 10%
其他(other)        ≤ budget × 5%
（预算低档 ≤2000 元时：住宿 ≤35%，门票 ≤15%，餐饮上浮 30%——穷人乐优先）
```
- 输入：`user_budget` + `days` + `style`（budget/comfort/luxury 分档系数）
- 输出：`BudgetAllocation`（5 项各带上限金额 + 每日上限）
- 位置：`services/agent/budget.py`（新模块，纯函数，无 LLM）

#### 注入点
1. `planner_prompt.build_planner_prompt`（L52）：新增"预算分解目标"段落，给出 5 项上限，并要求 budgetBreakdown 各分项 ≤ 对应上限
2. review 代码层（review.py:73-89）：从"总和 ≤ 1.15×budget"升级为 **分项校验**——任一单项超上限 → 打回，feedback 指明"哪一项超了多少"

**验收标准**：
- [ ] 预算分解器单测：边界（低/中/高档）、整除、sum(5 项上限) > budget（预留弹性）
- [ ] 生成行程中 budgetBreakdown 分项违规率（用真实后端 eval 抽样 20 例）从现状降到 ≤20%
- [ ] review 分项校验打回 feedback 含具体超支项与金额（单测）

### 5.3 P0-3 确定性预算修正器（Budget Corrector）

**目标**：超预算打回后，不再让 LLM 盲目重写，而是由代码层给出"目标分配 + 修正指令"。

#### 流程（替代 orchestrator.py:175-187 的裸 feedback 重写）
```
review 打回（超支）
  → BudgetCorrector.run(plan_result, allocation)
      ① 计算超支项与差额 over = totalBudget - 预算分解目标
      ② 生成降级目标：按轮次确定优先级
         R1 砍活动：tickets 上限收紧（×0.8），并列出应替换为免费景点的提示
         R2 降住宿：accommodation 目标 = 当前值 × (1 - min(0.35, over/当前值))
         R3 砍天数/时段：提示减少一个晚间付费活动
      ③ 输出 CorrectorAction { 目标分解表, 指令文本, 轮次 }
  → 注入 planner_input.feedback（含目标分解表 + 指令，而非泛泛"降低预算"）
  → PlannerAgent 仅重生成（配合 5.4 局部重生成）
  → review 再校验（≤3 轮，超过后强制返回）
```

#### 与竞品的差异（更优处）
- 竞品直接对价格数值打折（破坏数据真实性）；本项目**只改目标分解 + 让 LLM 在真实数据上重新组合**，保持费用真实性
- 竞品无分项概念；本项目按 5 项分解逐项收敛

**验收标准**：
- [ ] Corrector 输出确定（同输入同输出，单测）
- [ ] 超支行程经修正后 ≤2 轮内收敛到预算内（用 eval fixtures 中现存超支用例验证）
- [ ] 修正后的 budgetBreakdown 5 项齐全且总和 ≤ 1.0×budget（硬断言）

### 5.4 P1-1 局部重生成（打回成本优化）

**目标**：review 打回时只重写问题字段，不重写整个行程。

#### 设计
- 现有 `_merge_partial_plan`（orchestrator.py:457-505）已有按 day 号替换的机制，但 **plan() 主链路未用**（modify() 才用）
- 复用机制：打回重试时构造 `existing_trip`（原始行程）+ `target_days`（仅被修正影响的字段，如全量费用修正时走"budgetBreakdown-only 重生成"）
- 新增 `PlannerInput.revise_scope: full | budget_only | days`：budget_only 模式 prompt 只重生成费用项与受影响活动的 price，禁止改景点与天数

**验收标准**：
- [ ] 预算类打回走 budget_only 路径，行程景点/顺序 diff 为空（单测断言）
- [ ] 重试 token 成本下降 ≥40%（对比同用例全量重写）

### 5.5 P1-2 规划状态机显式化

**目标**：显式 8 态状态机，支撑流式进度与可观测性。

#### 设计
```
collecting → recommending → researching → planning → reviewing
  → adjusting（corrector 修正中）→ planning（重生成）
  → completed / failed
```
- 复用现有 `trip-generating-progress` 前端进度设计（docs/trip-generating-progress-design.html）
- orchestrator 内部回调 `on_state(state)` 发出进度事件；SSE 通道（recommend-stream）透传状态
- 与现有 review 循环、variants 流程兼容（variants 各自有状态副本）

**验收标准**：
- [ ] SSE 进度事件含显式状态字段（前端现有进度条可消费）
- [ ] 状态流转单调合法（状态机单测：非法跳转报错）

---

## 6. 工作量评估与里程碑

| 阶段 | 内容 | 预估 |
|---|---|---|
| M1 | P0-1 费用真实性链路（数据层 + 估算器 + costSource） | 3-4 天 |
| M2 | P0-2 预算分解器 + review 分项校验 | 2 天 |
| M3 | P0-3 预算修正器 + 重试循环改造 | 2-3 天 |
| M4 | P1-1 局部重生成（budget_only scope） | 1-2 天 |
| M5 | P1-2 状态机显式化 | 1-2 天 |
| 合计 | | 9-13 天 |

## 7. 风险与开放问题

| # | 风险/问题 | 应对 |
|---|---|---|
| 1 | **avg_cost 补全依赖 POI ETL 数据质量** | v1 允许估算兜底（标记 estimate），不阻塞；真实覆盖 ≥50% 即算达标 |
| 2 | **美团价格查询会增加 Research 延迟** | 仅酒店/交通 2 项可选接入，超时 3s 降级估算器；纳入 Research 并行工具组 |
| 3 | **分项校验可能过度收紧导致打回率上升** | 分项上限预留 1.15 弹性（单项 ≤ 上限×1.15 放行）；上线用 eval 对比打回率 |
| 4 | **budget_only 重生成可能改变活动价格与活动内容的耦合** | prompt 明确"仅改费用，活动内容保持不变"；diff 校验兜底 |
| 5 | 竞品循环中"打折与重搜语义冲突"的坑 | 本项目不复刻数值打折，只做目标分解 + 重组合，天然规避 |
| 6 | 状态机与现有 variants/stream 流程的兼容 | M5 前确认 progress 事件现有实现，增量改造 |

## 8. 遗留与后续（本期外）

- **P2 候选**：DestinationAgent 式 5 维评分（模糊意图"周末想出去逛逛"时给出 Top3 目的地候选）
- **P2 候选**：美团真实价格升级为生成链路必选（v1 只读可选）
- **P2 候选**：竞品 `error_messages` 汇总模式（并行工具失败时给用户可读的错误合并说明）

## 9. 参考

- 竞品代码：`python/orchestrator/budget_loop.py`、`python/agents/budget_agent.py`、`python/agents/activity_agent.py`、`python/orchestrator/parallel.py`
- 本地现状：`orchestrator.py:87-202, 175-187, 457-505`、`review.py:73-104`、`planner_prompt.py:84-135`、`knowledge_service.py:570`、`models/spot.py:52`
- 既有设计：`docs/多_agent_架构设计_2026-07-04_00-26.md:256-268`（曾规划 BudgetAgent 未实现）、`tasks/multi-variant-planning-tech-spec.md`、`docs/trip-generating-progress-design.html`
