# RAG 评估体系建设方案

> 参考：[小林面试笔记 - 怎么量化你的 RAG 效果？](https://xiaolinnote.com/ai/rag/18_evaluation.html)
> 项目基础：`trip-backend` (Python FastAPI)  
> 创建日期：2026-07-05

---

## 目录

1. [现状分析](#1-现状分析)
2. [三层评估架构](#2-三层评估架构)
3. [Phase 1：检索层评估（Hit@K + MRR）](#3-phase-1检索层评估hitk--mrr)
4. [Phase 2：生成层评估（RAGAs）](#4-phase-2生成层评估ragas)
5. [Phase 3：线上指标看板](#5-phase-3线上指标看板)
6. [CI 集成](#6-ci-集成)
7. [时间线 & 工作量估算](#7-时间线--工作量估算)

---

## 1. 现状分析

### 已有的评估体系

项目目前有一套 Agent Eval 框架（Node/Python 双实现），包含：

| 组件 | 数量 | 说明 |
|------|:----:|------|
| Evaluator | 13 个 | schema_check, poi_city_match, keyword_coverage, tool_call_audit, pace_consistency + 5 domain + 3 multi-turn |
| Fixture | 10 个 | YAML 格式测试用例，覆盖主流旅游场景 |
| Runner | 1 个 | 加载 fixture → 执行 mock/real agent → 逐 evaluator 评分 → 汇总报告 |
| CI 门禁 | 1 个 | Baseline 对比，默认 80% 通过率阈值 |
| RAG 组件测试 | 14 个 | query_rewriter, RRF, reranker, embeddings, chroma client 等单测 |
| RAG Benchmark | 1 个 | 15 查询 × 多城市的检索延迟压测（P50/P95/P99） |

### 现存缺口

| 维度 | 当前状态 | 目标状态 |
|------|---------|---------|
| **检索质量** | ❌ 无直接指标 | Hit@K, MRR |
| **生成质量** | ❌ 无直接指标 | Faithfulness, Answer Relevancy, Context Recall, Context Precision |
| **线上观测** | ⚠️ 有 Feedback 系统，但未形成指标看板 | 点踩率、追问率、转人工率等持续追踪 |

当前 Agent Eval 对 RAG 的覆盖是**间接的**：
- `tool_call_audit` → 检查 `retrieve_knowledge` 是否被调用（次数验证）
- `poi_city_match` → 检查 POI 是否属于正确城市（结果端验证）
- `keyword_coverage` → 检查关键词是否出现（内容覆盖验证）

这些验证了「Agent 是否正确使用了 RAG」，但**没有直接量化 RAG 检索和生成的质量**。

---

## 2. 三层评估架构

```
  ┌─────────────────────────────────────────────────────────┐
  │                    Layer 3: 线上指标                      │
  │  点踩率 · 追问率 · 转人工率 · 空回答率 · 高分低满意度      │
  │           复用现有 Feedback 系统 + 少量扩展                │
  └───────────────────────┬─────────────────────────────────┘
                          │ 最终验收
  ┌───────────────────────▼─────────────────────────────────┐
  │                Layer 2: 生成层 (RAGAs)                    │
  │  Faithfulness · Answer Relevancy · Context Recall/P      │
  │     新增 RAGAs Evaluator，接入现有 eval 框架              │
  └───────────────────────┬─────────────────────────────────┘
                          │ 定位生成层问题
  ┌───────────────────────▼─────────────────────────────────┐
  │              Layer 1: 检索层 (Hit@K + MRR)               │
  │      专用检索测试集 + 批量召回 → 指标计算 → 报告           │
  └─────────────────────────────────────────────────────────┘

  定位问题链路：
  Answer 不好 → Faithfulness 低 → Context Precision 低 → Hit@K 低
                 (生成层)         (检索噪音)          (检索召回)
```

### 三层的关系

| 层级 | 回答的问题 | 谁用 |
|------|-----------|------|
| Layer 1 检索层 | 检索有没有把正确内容找回来？ | 研发调优 Embedding/Chunking/Rerank |
| Layer 2 生成层 | LLM 有没有好好利用检索结果？ | 研发调优 Prompt/模型/幻觉 |
| Layer 3 线上层 | 用户觉得好不好用？ | PM & 运营决策 |

### 指标-问题定位矩阵

| 指标低 | 说明 | 优化方向 |
|--------|------|---------|
| **Hit@K 低** (<0.7) | 正确内容没召回 | 换 Embedding 模型 / 调 Chunking / 加多路召回 |
| **MRR 低** (<0.5) | 正确内容排在后面 | 加强 Rerank 模型 / 调整 Top-K 数量 |
| **Context Recall 低** (<0.7) | 检索覆盖不足 | 加多路召回 / 扩大检索范围 |
| **Context Precision 低** | 检索噪音多 | 调低 Top-K / 加强 Rerank / 加质量门控 |
| **Faithfulness 低** (<0.8) | LLM 编造幻觉 | 加强 Prompt 约束 / 引入引用核查 / 质量门控 |
| **Answer Relevancy 低** (<0.8) | 答案跑题 | 优化 System Prompt / 限定回答范围 |
| **点踩率高** | 用户不满意 → 看上面哪层出问题 | 综合排查 |

---

## 3. Phase 1：检索层评估（Hit@K + MRR）

### 3.1 目标

量化 RAG 检索质量，能回答：「检索到底好不好？换 Embedding 模型有没有进步？」

### 3.2 方案设计

```
                       ┌─────────────┐
                       │  测试数据集   │
                       │ {query, gold} │
                       └──────┬──────┘
                              │ 遍历每条 query
                              ▼
                    ┌───────────────────┐
                    │   search_spots()  │
                    │   (三路召回+RRF)   │
                    └────────┬──────────┘
                             │ 返回值名列表
                             ▼
                    ┌───────────────────┐
                    │   Hit@K / MRR 计算  │
                    └────────┬──────────┘
                             │
                             ▼
                    ┌───────────────────┐
                    │    评估报告        │
                    │  JSON + 控制台输出  │
                    └───────────────────┘
```

### 3.3 测试数据集

**数据来源**：从景点知识库抽取具有代表性的景点，为每个景点生成 3~5 个用户提问

初始数据规模：**~15 个景点，~60 条 query**

覆盖城市：北京、成都、西安、杭州、上海、三亚、丽江、桂林  
覆盖类别：景点、美食、住宿

Query 生成策略（LLM 辅助）：

| Query 类型 | 示例 | 数量/景点 |
|-----------|------|:---------:|
| 直接问景点名 | "介绍一下故宫" | 1 |
| 按特征提问 | "北京有什么古建筑" | 1 |
| 按需求提问 | "成都有适合带父母去的地方吗" | 1 |
| 模糊提问 | "西安哪里好玩" | 1 |
| 混合需求 | "上海有什么又好玩又能吃美食的地方" | 1 |

### 3.4 指标计算

```
Hit@K = (正确结果在 Top-K 内的 query 数) / (总 query 数)
  计算 K = 1, 3, 5, 10, 20 五个档位

MRR = (1/N) * Σ(1/rank_i)
  其中 rank_i 是第 i 个 query 的正确结果排名，未命中则 rank_i = ∞
```

### 3.5 输出

```json
{
  "title": "RAG Retrieval Evaluation Report",
  "timestamp": "2026-07-05T17:30:00+08:00",
  "config": {
    "dataset_size": 60,
    "k_values": [1, 3, 5, 10, 20]
  },
  "aggregated_metrics": {
    "hit_rate": { "k1": 0.45, "k3": 0.70, "k5": 0.82, "k10": 0.91, "k20": 0.96 },
    "mrr": 0.62
  },
  "per_query": [
    {
      "query": "介绍一下故宫",
      "gold": "故宫博物院",
      "gold_id": 1,
      "rank": 1,
      "hit_at_k": { "k1": true, "k3": true, "k5": true, "k10": true, "k20": true }
    }
  ],
  "recommendations": [...]
}
```

### 3.6 工作量

| 子任务 | 工作量 |
|--------|:------:|
| 构建测试数据集（含 LLM 生成 query） | ~2h |
| 实现 Hit@K 和 MRR 计算 | ~1h |
| 实现评估运行器和报告输出 | ~2h |
| **合计** | **~5h (~3 天)** |

---

## 4. Phase 2：生成层评估（RAGAs）

### 4.1 目标

量化 LLM 生成质量（幻觉、跑题、检索利用率），能回答：「Agent 的回答有没有编造？有没有好好利用检索回来的资料？」

### 4.2 方案设计

利用现有 Eval 框架的扩展点，新增 RAGAs evaluator：

```
Fixture → Real Agent → AgentOutput + retrieved_chunks
                               │
                               ▼
                    ┌─────────────────────┐
                    │  RAGAs Evaluator    │
                    │  (LLM-as-Judge)     │
                    └──┬──────┬──────┬───┘
                       │      │      │
                       ▼      ▼      ▼
                 Faithful.  Relv.   Recall
                  Score     Score    Score
                       │      │      │
                       └──────┴──────┘
                              ▼
                       EvalResult
                   (写入报告 + CI 门禁)
```

### 4.3 四指标详解

#### Faithfulness（忠实度）

判断答案中的每个事实是否都有检索到的 chunk 作为依据。

**方法**：LLM-as-Judge（使用 DeepSeek）

```
1. 将答案拆成若干陈述句（Claim Decomposition）
2. 对每个陈述问：这个陈述在给定的上下文 chunk 中能找到依据吗？
3. Faithfulness = 有依据的陈述数 / 总陈述数
```

**目标值**：> 0.8

#### Answer Relevancy（答案相关性）

判断答案是否回答了用户的问题，而不是答非所问。

**方法**：LLM-as-Judge

```
1. 给定 question 和 answer
2. 问 LLM：这个答案回答了问题吗？(1-5 分)
3. 归一化到 0-1
```

**目标值**：> 0.8

#### Context Recall（上下文召回率）

判断检索到的上下文是否覆盖了回答问题所需的所有信息。

**方法**：需要 ground truth 答案做参照，LLM 比较

**目标值**：> 0.7

#### Context Precision（上下文精确率）

判断检索结果中相关 chunk 的排序质量。

**方法**：基于 relevance 判断结果位置加权

**目标值**：> 0.7（配合 Precision 使用）

### 4.4 与现有框架的集成

在现有 YAML Fixture 中新增 `ragas_evaluator` 标签：

```yaml
# chengdu-3days-foodie-relaxed.yaml
evaluators:
  - schema_check
  - poi_city_match
  - keyword_coverage
  - tool_call_audit
  - pace_consistency
  - ragas_evaluator         # 新增
```

RAGAs 评估器的实现：

```python
@register_evaluator("ragas_evaluator")
def ragas_evaluator(output: AgentOutput, fixture: Fixture) -> EvalResult:
    # 1. 从 output 中提取 final_answer 和 retrieved_chunks
    # 2. 调用 LLM 计算 Faithfulness 和 Answer Relevancy
    # 3. 如果有 ground_truth，计算 Context Recall 和 Context Precision
    # 4. 汇总为 EvalResult
```

### 4.5 token 成本估算

| 指标 | 每条调用 | 60 条评估 |
|------|:--------:|:---------:|
| Faithfulness | ~800 tokens (DeepSeek) | ~48K tokens (~¥0.05) |
| Answer Relevancy | ~400 tokens | ~24K tokens (~¥0.025) |
| **合计** | ~1200 tokens | ~72K tokens (~¥0.075) |

成本很低，可以放心全量跑。

### 4.6 工作量

| 子任务 | 工作量 |
|--------|:------:|
| 实现 Faithfulness 评估器 | ~3h |
| 实现 Answer Relevancy 评估器 | ~2h |
| 实现 Context Recall/Precision 评估器 | ~2h |
| 编写单元测试 | ~2h |
| 集成到现有 Fixture 和 CI | ~1h |
| **合计** | **~10h (~4 天)** |

---

## 5. Phase 3：线上指标看板

### 5.1 目标

将用户的真实反馈转化为可追踪的线上指标，与离线评估形成闭环。

### 5.2 方案设计

利用现有的 Feedback 系统（已完成）：

| 端点 | 数据 |
|------|------|
| `POST /api/feedback` | 提交点赞/点踩（已有 `rating` 字段） |
| `GET /api/feedback/admin/daily-stats` | 每日统计趋势 |
| `GET /api/feedback/admin/high-token-low-satisfaction` | 高分低满意度案例 |
| `POST /api/feedback/admin/test-alert` | 告警检测 |
| Alert Scheduler | 定时后台告警调度 |

### 5.3 新增指标

| 线上指标 | 计算方式 | 优先级 |
|----------|---------|:------:|
| **点踩率** | `dislikes / (likes + dislikes)` × 时间段 | P0 ✓ 已有 |
| **高分低满意度** | Token 消耗 > P90 且 点踩 = 效率低 | P0 ✓ 已有 |
| **空回答率** | Agent 输出为空或"I don't know"的占比 | P1 |
| **转人工率** | 用户触发了转人工操作的占比 | P2（需前端配合） |
| **会话解决率** | 同一 session 中用户没追问的比例 | P2 |

### 5.4 看板实现

前端页面：在现有 AdminFeedbackDashboard 基础上增加趋势图

```
Admin Feedback Dashboard
├── 概要卡片: 总反馈数 / 点赞数 / 点踩数 / 点踩率
├── 趋势图: 每日点踩率变化（7天/30天）
├── 高分低满意度列表: Token高 + 分数低的案例
└── RAG 质量看板（新增）
    ├── 当前检索通过率 (Phase 1)
    ├── 当前 Faithfulness 得分 (Phase 2)
    └── 点踩率趋势叠加
```

### 5.5 工作量

| 子任务 | 工作量 |
|--------|:------:|
| 新增空回答率端点 | ~1h |
| 前端看板扩展 | ~3h |
| 告警规则完善 | ~1h |
| **合计** | **~5h (~2 天)** |

---

## 6. CI 集成

所有 Phase 的评估结果都应纳入 CI 流水线，形成自动化门禁。

### 现有 CI 基础

```yaml
# .github/workflows/eval-nightly.yml
- 每晚定时运行 eval
- 支持 mock/real 两种模式
- result 对比 baseline，通过率 < 80% 触发告警
```

### Phase 1 CI 集成

```yaml
# 在 eval-nightly.yml 中新增
- name: Retrieval Evaluation
  run: |
    python -m eval.retrieval.run --save
    python scripts/eval_compare.py \
      --report eval-reports/retrieval-latest.json \
      --baseline eval-reports/retrieval-baseline.json \
      --threshold 0.7
```

### Phase 2 CI 集成

沿用现有 fixture + evaluator 模式，天然支持 CI。

### Phase 3 CI 集成

线上指标不直接进 CI 门禁，但可设置告警规则（例如点踩率超过 10% 触发飞书通知）。

---

## 7. 时间线 & 工作量估算

### 总览

```
Phase   | 内容                 | 工作量 | 周期   | 产出
────────┼──────────────────────┼────────┼────────┼─────────────────────────
Phase 1 | 检索层 Hit@K + MRR   | ~5h    | 3 天   | 检索评估脚本 + 第一份报告
Phase 2 | 生成层 RAGAs         | ~10h   | 4 天   | 4 个新 evaluator + 测试
Phase 3 | 线上看板             | ~5h    | 2 天   | 点踩率趋势 + 看板页面
────────┼──────────────────────┼────────┼────────┼─────────────────────────
合计    |                      | ~20h   | 9 天   | 完整三层评估体系
```

### 依赖关系

```
Phase 1 ──────┐
               ├── 无依赖（独立模块）
Phase 2 ──────┤
               ├── 依赖现有 eval 框架（已就绪）
Phase 3 ──────┘
               └── 依赖现有 feedback 系统（已就绪）
```

三个 Phase 互不阻塞，可并行推进。

### 输出文件

| 文件 | 说明 |
|------|------|
| `eval/retrieval/dataset.py` | 检索测试数据集 |
| `eval/retrieval/metrics.py` | Hit@K, MRR 计算 |
| `eval/retrieval/run.py` | 检索评估 CLI |
| `eval-reports/retrieval-baseline.json` | 检索评估基线 |
| `eval/evaluators/ragas.py` | RAGAs 评估器（Phase 2） |
| 前端看板组件 | 线上指标可视化（Phase 3） |
