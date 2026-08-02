# 预算控制引擎 + 费用真实性链路 — 技术设计文档（TDD）

> **文档状态**：已实施（2026-08-01，T1-T9 完成；实施任务见 tasks/budget-control-and-cost-fidelity-plan.md）
> **日期**：2026-08-01
> **对应 PRD**：`docs/budget-control-and-cost-fidelity-prd.md`（P0 三项，P1 两项延期）
> **下游消费者**：后端（trip-backend，本期无前端改动）
> **主理人已确认**：① P0 三项全部纳入本期；② 美团价格先只读（生成链路不主动调美团）

---

## 0. 精读实现后的关键发现

### 0.1 预算链路现状

| 环节 | 位置 | 说明 |
|---|---|---|
| 入口校验 | `trip_service.py:383`、`schemas/trip.py:14` | 预算 50~1,000,000 元硬校验，无分项概念 |
| prompt 约束 | `planner_prompt.py:84-135` | 仅"预算：X 元" + budgetBreakdown 5 字段规则，无分项上限 |
| 酒店预算推算 | `research_agent.py:135-137` | `hotel_budget = budget/days/1.5`，唯一的确定性分摊，但只影响酒店搜索不约束生成 |
| 预算校验 | `review.py:73-89` | 代码层仅 `totalBudget/budget > 1.15` 总和校验；feedback 为自由文本"优先降低酒店档次、增加免费景点、减少付费活动" |
| 打回重试 | `orchestrator.py:175-187` | `MAX_REVIEW_RETRIES = 2`（最多 3 轮）；feedback 注入 `planner_input.feedback` 后 **PlannerAgent 全量重写**；最后一轮仍失败返回带 issues 行程 |
| 局部修改预算重算 | `orchestrator.py:495-503` | modify() 增量重算，正常，不涉及本期 |

### 0.2 费用链路现状（金额全部是 LLM 编的）

| 发现 | 位置 | 说明 |
|---|---|---|
| `spots.avg_cost` 填充率 1.7% | `models/spot.py:52-57` | 30,791 条中仅 532 条有值 |
| RAG 检索不输出价格 | `knowledge_service.py:570` | `_rating_search` SELECT 无 `avg_cost`；`format_search_results`（L752-787）无价格字段 |
| 酒店数据无价格 | `data/poi_raw/*.json` | 仅地址/坐标/类型/评分 |
| 唯一真实费用 | `tools/calculate_distance.py:93-110, 182-205` | 交通费按公里×单价粗算（cost_min/cost_max） |
| 美团 Skill | `.claude/skills/meituan-travel/` | 有真实价格能力，生成链路未调用（本期保持只读） |
| `PlanResult` 无来源字段 | `schemas.py:60` | 费用项无 costSource 概念 |

### 0.3 测试基础设施

| 项目 | 说明 |
|---|---|
| 测试框架 | pytest + pytest-asyncio，`tests/conftest.py` 起真实 PostgreSQL（trip_test_db）+ 每次建表 |
| 现有相关测试 | `test_orchestrator_variants.py`（9 条）、`test_trip_service_variants.py`（12 条）、`test_planner_agent_variant.py`（7 条） |
| eval fixtures | `eval/fixtures/trip-planning/` 10 个 YAML，其中 `tokyo-5days-budget-tight.yaml` 是现成的预算约束用例 |
| LLM mock 模式 | `eval/run.py --mock` 支持无 LLM 跑 Agent 链路（预算修正器可先用 mock 验证确定性） |

### 0.4 关键约束（设计前提）

1. **"代码能判的绝不用 LLM"**（`review.py:3-8` 注释）——项目一贯原则，预算控制必须确定性
2. **架构文档曾规划 BudgetAgent 未实现**（`docs/多_agent_架构设计_2026-07-04_00-26.md:256-268`）——本期评估后仍不引入 LLM Agent（见 2.2）
3. **无 Alembic**，建表走 `Base.metadata.create_all`（`create_tables.py`）——本期**不改 DB schema**，规避迁移问题

---

## 1. 方案对比

### 方案 A：独立纯函数预算控制器模块（**推荐**）

新增 `src/services/agent/budget/` 包，全部纯函数、无 LLM、无 IO：

| 模块 | 职责 | 集成点 |
|---|---|---|
| `allocator.py` | 预算分解器：budget/days/style → 5 项上限 | `planner_prompt.build_planner_prompt` 注入 prompt；review 分项校验基准 |
| `corrector.py` | 预算修正器：plan + allocation → `CorrectorAction`（目标分解 + 结构化指令 + 轮次） | `orchestrator.py:175-187` 重试循环，替换裸 feedback |
| `cost_estimator.py` | 费用估算器：spot/城市/类别 → 估算价 + costSource | `knowledge_service.format_search_results` 附加 avg_cost/估算价 |
| `budget_controller.py` | 组装层：编排 allocator + corrector + review 打回信息 | `orchestrator.plan()` 调用 |

**改动映射**：

| 层级 | 改动 | 文件 |
|---|---|---|
| 新模块 | budget/ 包 4 文件（纯函数） | `src/services/agent/budget/*.py` |
| Schema | `PlanResult` 费用项新增 `costSource` 枚举字段；新增 `BudgetAllocation`/`CorrectorAction` | `schemas.py` |
| 检索 | `_rating_search` SELECT 加 `avg_cost`；`format_search_results` 输出价格 + 估算兜底 | `knowledge_service.py` |
| 校验 | review 新增分项校验（替代/补充 1.15 总和校验），feedback 结构化 | `review.py` |
| 提示词 | 注入预算分解目标段落 | `planner_prompt.py` |
| 编排 | 重试循环接入 corrector，打回信息结构化注入 | `orchestrator.py:175-187` |
| 测试 | 新增 5 个测试文件（见 §5） | `tests/test_budget_*.py` |

### 方案 B：新增独立 BudgetAgent（LLM Agent）

参考竞品，新增第 4 个 Agent：预算校验 + 调整建议全部走 LLM（独立 system_prompt + schema + LLM 调用），Orchestrator 每轮调它。

**改动映射**：`agents/budget_agent.py` 新增 + `orchestrator.py` 重试循环改为调 Agent + `schemas.py` 新增 BudgetReviewInput/Output。

### 方案 C：纯提示词 + 校验强化（不新增模块）

只改两处：① prompt 里写死预算分解公式（"住宿不超过 40%"等文字）；② review 增加分项校验。

**改动映射**：`planner_prompt.py` + `review.py`，其余零改动。

---

## 2. 推荐方案与理由

### 推荐：**方案 A**

| 维度 | A | B（LLM Agent） | C（纯提示词） |
|---|---|---|---|
| 确定性 | ✅ 纯函数，输出可断言 | ❌ LLM 输出不确定，打回率无保证 | ❌ 只有源头约束，无修正能力 |
| 费用真实性支撑 | ✅ 估算器解决 avg_cost 缺失 | ❌ 费用仍是编的（Agent 无真实数据可查） | ❌ 无 |
| 每轮打回成本 | ✅ 结构化指令 + 目标分解，命中率高 | ❌ 每轮多一次 LLM 调用（token+延迟） | — |
| 可测试性 | ✅ 红→绿纯函数单测 | ❌ 需 mock LLM | ✅ 但只能测 review |
| 与项目原则契合 | ✅ "代码能判的绝不用 LLM" | ❌ 与 review.py 注释原则相悖 | ✅ 部分契合 |
| 收敛保证 | ✅ CorrectorAction 确定性 + ≤3 轮 | ❌ 依赖 LLM 状态 | ❌ 无修正环节 |
| 改动面/风险 | 🟡 5 文件 + 4 新模块（均为注入点，主流程签名不变） | 🔴 新 Agent 接入编排 + 状态管理 | 🟢 最小 |

**核心理由**：

1. **PRD 的第一目标是"确定性"** —— 竞品的核心价值正是确定性降级循环。方案 A 把 allocator/corrector 做成纯函数，输入输出可断言，收敛有保证；方案 B 把核心逻辑交给 LLM，等于放弃竞品最值得借鉴的东西。
2. **费用真实性是预算控制的前提** —— 只有方案 A 的 `cost_estimator` 能解决"LLM 无价可抄只能编"的根本问题（avg_cost 1.7% 填充率 + 检索不输出价格）。方案 B/C 做的预算控制控制的是假数字。
3. **方案 C 缺闭环** —— 只约束源头不修正结果，超支打回后仍回到"LLM 盲目全量重写"的现状，PRD 的 P0-3 落空。
4. **与项目既有原则一致** —— `review.py` 明确"代码能判的绝不用 LLM"；budget 三项全部可由代码判定，引入 BudgetAgent 是反模式。
5. **渐进式集成风险低** —— 方案 A 只在 3 个注入点（prompt 构建 / review / 重试循环）改动，`plan()/modify()/plan_variants()` 对外签名不变，variants 流程天然兼容（各 variant 独立重试循环，各自走 corrector）。

---

## 3. 方案 A 详细设计

### 3.1 数据契约（schemas.py 新增）

```python
# 费用来源枚举
class CostSource(str, Enum):
    RAG        = "rag"         # spots.avg_cost 真实值
    MEITUAN    = "meituan"     # 美团查得真实价（本期不主动查，仅保留枚举）
    ESTIMATE   = "estimate"    # cost_estimator 估算
    DISTANCE   = "distance"    # calculate_distance 交通粗算（既有）

# PlanResult 费用项统一挂 source（在既有字段旁新增，不破坏现有消费者）
class ActivityItem:  # 现状字段不变
    ...
    costSource: Optional[CostSource] = None

# 预算分解目标（allocator 输出）
class BudgetAllocation(BaseModel):
    budget: int
    days: int
    style: str
    allocation: dict[str, int]      # accommodation/food/transportation/tickets/other → 上限金额
    daily_activity_limit: int       # 每日活动费用上限
    elasticity: float = 1.15        # 单项弹性系数（单项 ≤ 上限×1.15 放行）

# 预算修正动作（corrector 输出）
class CorrectorAction(BaseModel):
    round: int                                  # 1/2/3
    over_amount: int                            # 超支金额
    target_allocation: dict[str, int]           # 本轮目标分解（5 项上限，已降级）
    instructions: str                           # 结构化中文指令（给 PlannerAgent）
    keep_scope: str = "full"                    # 预留 P1 局部重生成字段，本期恒为 full
```

### 3.2 预算分解器 allocator.py

```python
def allocate(budget: int, days: int, style: str = "comfort") -> BudgetAllocation:
    """确定性预算分解。返回 5 项上限（金额取整到 10 元）。"""
    # 基础占比（总和 100%）
    RATIO = {"accommodation": 0.40, "food": 0.25,
             "transportation": 0.20, "tickets": 0.10, "other": 0.05}
    # style 系数（budget 穷人乐 / comfort 均衡 / luxury 重住宿）
    if style == "budget":
        RATIO = {"accommodation": 0.35, "food": 0.30,
                 "transportation": 0.15, "tickets": 0.15, "other": 0.05}
    elif style == "luxury":
        RATIO = {"accommodation": 0.50, "food": 0.20,
                 "transportation": 0.15, "tickets": 0.10, "other": 0.05}
    # 预算≤2000 低档兜底（与 PRD 一致）
    if budget <= 2000: RATIO["tickets"] = 0.15; RATIO["food"] += 0.05; ...
    allocation = {k: round_to_10(budget * r) for k, r in RATIO.items()}
    daily_activity_limit = round_to_10(budget / days * 0.30)
    return BudgetAllocation(...)
```

> 设计要点：分项上限和 ≥ budget（因向下取整到 10 元，和略小；elasticity 1.15 覆盖）。**不打折金额，只定目标**——区别于竞品直接改 price。

### 3.3 预算修正器 corrector.py

```python
def build_correction(plan: PlanResult, alloc: BudgetAllocation, round: int) -> CorrectorAction:
    """输入：LLM 生成的行程 + 预算分解目标 + 当前轮次。
    输出：确定性降级目标 + 结构化指令（不回写任何金额）。"""
    over = plan.totalBudget - alloc.budget
    targets = dict(alloc.allocation)
    # 轮次优先级（借鉴竞品渐进式，适配 5 项分解）
    if round == 1:
        targets["tickets"]  = int(alloc.allocation["tickets"] * 0.6)   # 砍门票：免费景点替换
        targets["food"]     = int(alloc.allocation["food"] * 0.9)      # 收紧餐饮
    elif round == 2:
        targets["accommodation"] = int(alloc.allocation["accommodation"] * 0.7)  # 降住宿档
    else:  # round == 3
        targets["transportation"] = int(alloc.allocation["transportation"] * 0.8)
        targets["other"]          = 0
    instructions = build_instructions(round, over, targets)  # 结构化中文指令，含各分项目标金额
    return CorrectorAction(round=round, over_amount=over,
                           target_allocation=targets, instructions=instructions)
```

> 与竞品差异：竞品直接 `price *= (1-cut_ratio)`（破坏真实性）；本方案只输出**目标分配 + 指令**，由 PlannerAgent 在真实数据上重新组合，保住 costSource 可信度。

### 3.4 费用估算器 cost_estimator.py

```python
CITY_TIER = {  # 城市消费档位（从既有数据推导，一线/新一线/二三线）
    "high":    {"attraction": 80, "food_per": 120, "hotel_night": 400},
    "medium":  {"attraction": 50, "food_per": 80,  "hotel_night": 250},
    "low":     {"attraction": 30, "food_per": 50,  "hotel_night": 150},
}

def estimate_cost(spot: dict, city_tier: str, category: str) -> tuple[int, CostSource]:
    """返回 (估算金额, 来源)。有 avg_cost → (真值, RAG)；无 → (类别默认值, ESTIMATE)。"""
    if spot.get("avg_cost"): return (spot["avg_cost"], CostSource.RAG)
    default = CITY_TIER[city_tier][category]
    return (default, CostSource.ESTIMATE)

def enrich_search_results(results: list[dict], city_tier: str) -> list[dict]:
    """knowledge_service.format_search_results 调用：每条附加 avg_cost + costSource。"""
```

### 3.5 review 分项校验改造（review.py:73-104）

```python
# 现状（保留，转为"总和硬上限"兜底）：
#   totalBudget/budget > 1.15 → 打回
# 新增（分项校验，feedback 结构化）：
def _check_budget_items(plan, alloc: BudgetAllocation) -> Optional[BudgetViolation]:
    violations = []
    for key, limit in alloc.allocation.items():
        actual = plan.budgetBreakdown.get(key, 0)
        if actual > limit * alloc.elasticity:
            violations.append(BudgetViolation(key=key, actual=actual, limit=limit, over=actual-limit))
    if violations:
        return BudgetViolationResult(
            passed=False,
            over_amount=sum(v.over for v in violations),
            violations=violations,
            feedback=f"预算分项超标：{'、'.join(f'{v.key} 超 {v.over} 元' for v in violations)}。"
                     f"目标：{alloc.allocation}。请按目标重新分配预算。"
        )
```

> 打回 feedback 从自由文本 → 结构化（含分项超支明细 + 目标分解），供 3.6 的 corrector 消费，也供日志/评估分析。

### 3.6 orchestrator 重试循环改造（orchestrator.py:175-187）

```
现状：review 失败 → feedback 自由文本 → planner_input.feedback → PlannerAgent 全量重写
改造：review 失败 → corrector.build_correction(plan, alloc, round)
      → planner_input.budget_correction = CorrectorAction（新字段）
      → planner_prompt 检测 budget_correction 存在 → 渲染"预算修正指令"段落
      → PlannerAgent 重写（含目标分解，不再裸提示"降低预算"）
      → review 再校验（≤3 轮，MAX_REVIEW_RETRIES 不变；超限返回带 issues，行为保持）
```

### 3.7 prompt 注入（planner_prompt.py:84-135）

新增段落（allocator 输出渲染）：

```
【预算分解目标】（必须遵守，各分项不得超过上限）
- 总预算：12000 元
- 住宿 ≤ 4800 | 餐饮 ≤ 3000 | 交通 ≤ 2400 | 门票 ≤ 1200 | 其他 ≤ 600
- 每日活动费用 ≤ 720 元
【预算修正指令】（第 N 轮，上一轮超支 X 元）
- 门票目标收紧至 ≤ 720，优先替换为免费景点：...
```

---

## 4. 不改动的范围（明确排除）

| # | 排除项 | 原因 |
|---|---|---|
| 1 | **P1-1 局部重生成**（budget_only scope） | 主理人确认本期只做 P0 三项；`CorrectorAction.keep_scope` 字段已预留 |
| 2 | **P1-2 规划状态机显式化** | 同上，延期 |
| 3 | **DB schema 改动**（不加表/不加列） | `costSource` 随 `trips.content` JSON 存储，不落结构化列；规避无 Alembic 的迁移问题 |
| 4 | **美团真实价格接入生成链路** | 主理人确认"先只读"：`meituan-travel` Skill、Research 工具组、prompt 均不新增美团调用；`CostSource.MEITUAN` 仅预留枚举 |
| 5 | **前端改动**（trip-front 零改动） | `costSource` 作为新字段透传，现有消费者忽略未知字段；前端展示/过滤排期到后续 |
| 6 | **orchestrator 对外签名与流程结构** | `plan()/modify()/plan_variants()` 入口、返回结构不变；仅重试循环内部注入 corrector |
| 7 | **ChatAgent 对话链路** | 对话中的预算处理不在本期（与 6 同因，保持改动面收敛） |
| 8 | **modify() 局部修改链路** | 其增量预算重算已工作；本期不动 |
| 9 | **缓存体系** | `research_bundle_cache`、Redis 均不涉及预算链路，不动 |
| 10 | **新依赖** | 不新增任何 pip/npm 依赖（纯 Python 标准库 + 现有 pydantic） |
| 11 | **竞品数值打折策略** | 明确不复刻"直接改 price"方案（破坏数据真实性），只做目标分解 + 重组合 |
| 12 | **variants 流程** | 3 variant 串行结构、selection 页面、confirm/discard 闭环均不变；各 variant 重试循环自动获得 corrector 能力 |

---

## 5. TDD 测试设计（先写测试，红→绿）

### 5.1 测试文件与用例清单

**`tests/test_budget_allocator.py`**（纯函数，8 条）

| # | 用例 | 断言 |
|---|---|---|
| A1 | 默认 comfort 中档预算 10000/5天 | 5 项= [4000,2500,2000,1000,500]±10 元；sum ≈ budget |
| A2 | budget 风格（穷人乐） | accommodation 35% 且 tickets 15% 且 food 30% |
| A3 | luxury 风格 | accommodation 50% |
| A4 | 预算 ≤2000 低档兜底 | tickets=15%，food 上浮 |
| A5 | 确定性：同输入两遍 | 输出 deep-equal |
| A6 | daily_activity_limit | = round10(budget/days×0.30) |
| A7 | 边界：budget=50（最低） | 无负值、全字段 ≥0 |
| A8 | elasticity 默认 1.15 | 可覆盖 |

**`tests/test_budget_corrector.py`**（纯函数，8 条）

| # | 用例 | 断言 |
|---|---|---|
| C1 | 超支 20% 第 1 轮 | tickets 目标 = alloc×0.6；food ×0.9；其余不变 |
| C2 | 第 2 轮 | accommodation ×0.7 |
| C3 | 第 3 轮 | transportation ×0.8 且 other=0 |
| C4 | over_amount 计算正确 | = totalBudget - alloc.budget |
| C5 | 确定性 | 同输入同输出 |
| C6 | 轮次越界（>3） | 返回 round=3 行为（不崩溃） |
| C7 | instructions 含各分项目标金额 | 断言字符串包含关键分项数字 |
| C8 | 不修改入参 plan（无副作用） | 调用后 plan.totalBudget/budgetBreakdown 不变 |

**`tests/test_cost_estimator.py`**（纯函数，7 条）

| # | 用例 | 断言 |
|---|---|---|
| E1 | spot 有 avg_cost | 返回 (真值, RAG) |
| E2 | spot 无 avg_cost + 城市 high 档 | (类别默认值, ESTIMATE) |
| E3 | 城市档位差异 | high ≠ low 的默认价 |
| E4 | 类别差异 | attraction ≠ hotel_night |
| E5 | enrich_search_results | 每条都附加 avg_cost + costSource |
| E6 | 确定性 | 同输入同输出 |
| E7 | avg_cost=0 视为缺失 | 走 ESTIMATE |

**`tests/test_review_budget_items.py`**（复用现有 review 测试基建，7 条）

| # | 用例 | 断言 |
|---|---|---|
| R1 | 单项超限 >1.15 | passed=False，feedback 含具体项+金额 |
| R2 | 单项超限但 ≤1.15 弹性 | passed=True（放行） |
| R3 | 多项超限 | violations 列表齐全，over_amount=sum |
| R4 | 全部合规 | passed=True，无 budget feedback |
| R5 | budgetBreakdown 缺项（既有行为） | 保持现状校验 |
| R6 | 总和 >1.15（既有兜底） | 仍打回（保留原有断言） |
| R7 | 分项校验与 LLM review 共存 | LLM review 只记 warning 行为不变 |

**`tests/test_orchestrator_budget_loop.py`**（集成，6 条，mock LLM 模式）

| # | 用例 | 断言 |
|---|---|---|
| O1 | 行程超支 → 重试循环注入 budget_correction | planner_input 第 2 次调用含 CorrectorAction（用 fake planner 捕获） |
| O2 | 修正后收敛 | review 通过，final 返回 within budget |
| O3 | 2 轮后仍不收敛 | 返回带 issues（行为与现状一致，不崩） |
| O4 | 预算内行程 | 不触发 corrector（第 1 次即通过） |
| O5 | variants 各 variant 独立修正 | variant B 超支不影响 variant A（复用现有 variants 测试基建） |
| O6 | allocator 参与 review 分项校验 | 集成点接线正确 |

**`tests/test_cost_source_contract.py`**（契约，5 条）

| # | 用例 | 断言 |
|---|---|---|
| S1 | PlanResult 序列化含 costSource 字段 | 新字段默认 None，不破坏现有反序列化 |
| S2 | knowledge_service 检索返回含 avg_cost | `_rating_search` SQL 输出含 avg_cost 键 |
| S3 | 既有 fixtures 反序列化兼容 | 存量 YAML 行程无 costSource 也能解析（向后兼容） |
| S4 | CostSource 枚举值 | 4 个合法值 |
| S5 | 前端 SSE 透传 | 现有序列化不含新字段时前端不崩（回归） |

### 5.2 测试数据

- 复用 `eval/fixtures/trip-planning/tokyo-5days-budget-tight.yaml`（现成超预算用例，做 O1-O3 的输入来源）
- 新建 `tests/fixtures/` 内联 dict 样本：超支 PlanResult（构造 5 项中 tickets 超 200%）、合规 PlanResult

### 5.3 测试命令

```bash
cd trip-backend
uv run pytest tests/test_budget_allocator.py tests/test_budget_corrector.py \
  tests/test_cost_estimator.py -v          # 纯函数层（不依赖 DB）
uv run pytest tests/test_review_budget_items.py tests/test_orchestrator_budget_loop.py \
  tests/test_cost_source_contract.py -v    # 集成层（需 trip_test_db）
uv run python -m eval.run --real --tag budget  # 新增 budget tag 的 eval fixtures 回归
```

---

## 6. 验收标准（技术层面）

- [ ] 纯函数层 23 条用例红→绿（allocator 8 + corrector 8 + estimator 7）
- [ ] 集成层 18 条用例红→绿（review 7 + orchestrator 6 + contract 5）
- [ ] 现有测试全量回归通过（`uv run pytest tests/ -v`），零破坏
- [ ] eval fixtures 全量通过（含 `tokyo-5days-budget-tight`）
- [ ] 生成行程中费用项 ≥90% 带 costSource，门票来源 RAG 占比 ≥50%（抽样 20 例真实后端）
- [ ] 超支行程经 corrector 修正 ≤2 轮内收敛（预算内）≥80%（抽样 10 例）
- [ ] 确定性验证：同输入 run 两次，allocator/corrector/estimator 输出完全一致

## 7. 风险清单

| # | 风险 | 应对 |
|---|---|---|
| 1 | 分项校验收紧导致打回率上升（LLM 常把门票写高） | elasticity 1.15 缓冲；上线后对比 eval 打回率，必要时放宽 tickets |
| 2 | LLM 不遵守修正指令（不按 target_allocation 重写） | 第 3 轮后保持现状"带 issues 返回"兜底；统计遵守率，若 <60% 考虑 P1 局部重生成 |
| 3 | knowledge_service 改动影响现有 RAG 输出格式 | costSource 为附加字段，LLM 上下文仅新增一行价格文本；既有断言回归 |
| 4 | city_tier 推导不准 | 从现有数据分布直接推导（用 SQL 按 avg_cost 有值样本分位），写进文档；数据驱动非拍脑袋 |
| 5 | 估算价与真实价偏差大被用户感知 | costSource=estimate 明确标记 + 展示层后续处理（本期前端不展示） |

## 8. 实施顺序建议（TDD 节奏，先红后绿）

| 步 | 任务 | 红→绿 | 依赖 |
|---|---|---|---|
| T1 | 测试先行：`test_budget_allocator.py` → `allocator.py` | ✅ | — |
| T2 | `test_budget_corrector.py` → `corrector.py` | ✅ | T1 |
| T3 | `test_cost_estimator.py` → `cost_estimator.py` | ✅ | — |
| T4 | `test_review_budget_items.py` → review 分项校验 | ✅ | T1 |
| T5 | schemas 契约（BudgetAllocation/CorrectorAction/costSource） | 先改契约后接线 | T1-T4 |
| T6 | `test_orchestrator_budget_loop.py` → orchestrator 重试循环改造 | ✅ | T2+T4 |
| T7 | `test_cost_source_contract.py` → knowledge_service 暴露 avg_cost + prompt 注入 | ✅ | T3+T5 |
| T8 | eval fixtures 回归 + budget tag 新增 | 收尾 | 全部 |

## 9. 待决策项

| # | 问题 | 建议 |
|---|---|---|
| D1 | 分项校验是否**替换** 1.15 总和校验（改为：分项全过 = 总和必然 ≤1.15×budget？） | 保留总和兜底（双保险），R6 用例已覆盖 |
| D2 | `budget_correction` 走 `planner_input.feedback` 还是新增 `planner_input.budget_correction` 字段 | 新增字段（结构化，与自由文本 feedback 分离） |
| D3 | costSource 是否进 LLM 上下文（prompt 展示价格来源） | 进（一行文本），让 LLM 引用真价 |
| D4 | city_tier 落库（spots 表加列）还是纯运行时推导 | 纯运行时推导（不改 schema，见 §4-#3） |
