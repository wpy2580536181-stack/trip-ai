# LLM-as-Judge 评估补强 — 设计文档

> 2026-07-02 · 项目：Trip — AI 智能旅行规划系统
> 关联文档：[`docs/agent-eval.md`](../agent-eval.md)（eval 框架说明，TODO 见 §11.第三阶段）

## 1. 概述

为现有 eval 框架补强 **语义评估能力**。引入 LLM-as-Judge 评估 4 个规则 evaluator 抓不到的质量维度（行程可行性、约束遵循、表达可读性、个性化），与现有 13 个 rule-based evaluator **并行运行**、**不取代**。

### 1.1 目标

- **补全语义盲区**：规则 evaluator 只能查结构 / 关键词 / 工具调用 / 字段存在性，语义合理性需要 LLM 评估
- **可量化趋势**：1-5 分制可被 `ReportSummary` 聚合、看跨 PR/nightly 的趋势
- **可定位问题**：每条评分必须引用 agent 输出原文，避免"分数下降但不知道为什么"

### 1.2 非目标

- 不取代 13 个 rule-based evaluator
- 不做在线用户反馈打分（在线反馈另有 [`docs/online-feedback.md`](../online-feedback.md)）
- 不接 LangSmith / LangFuse
- 不做 A/B 测试自动决策

## 2. 现状背景

### 2.1 已有评估体系（截至 2026-07-02）

- 10 fixture × 13 evaluator（5 通用 + 5 领域 + 3 多轮/反例）
- 真实 eval pass rate：**单采 50-70% / 3 采多数 60-70%**
- DeepSeek prompt cache hit rate：~85% baseline
- Token 预算：5 万/小时

### 2.2 痛点

| 痛点 | 典型 case | 规则 evaluator 失败原因 |
|---|---|---|
| 行程"看起来过"但**节奏不可行** | Day1 上午 3 个远距离景点 + 午餐时间不够 | `pace_consistency` 只看活动数，不看距离/时间 |
| 约束**写在了文本但没真考虑** | "宠物友好"推荐了不允许宠物入内的咖啡店 | `pet_constraint_check` 查关键词而非实际可行性 |
| 文案**通顺但信息密度低** | "Day1 上午去一个美丽的地方" | 没有 evaluator 评估文字质量 |
| 推荐**没体现用户偏好** | 用户说"不喜欢博物馆"但 Day 全是博物馆 | 没有 evaluator 评估个性化 |

### 2.3 已有的"LWM judge 入口"（待启用）

- `eval/types.ts:111` 的 `EvalResult.details` 字段已为 LLM judge 留位
- `eval/types.ts:140` 的 `ReportSummary.byEvaluator` 已支持任意 evaluator 聚合
- `eval/registry.ts` 注册表模式可平移

## 3. 架构

### 3.1 数据流

```
runner.runFixture(fixture, sampleIdx)
  │
  ├─► agentFn(output)  (已有)
  │
  ├─► for each rule-based evaluator:    (已有)
  │     ├─ schema_check
  │     ├─ poi_city_match
  │     └─ ...  (13 个)
  │
  └─► llmJudgeEvaluator(output, fixture):   (新增)
        │
        ├─► judgeCache.get(fixtureId + inputHash)   ─► 命中 → 直接返回 4 维
        │
        ├─► judgeClient.evaluate(...)               ─► 1 次 LLM 调用
        │     ├─ timeout 30s, retry 2x
        │     └─ 解析 JSON 响应
        │
        ├─► judgeCache.set(...)
        │
        └─► return 4 个 EvalResult 共享同一 details.dimensions
```

### 3.2 组件清单

| 文件 | 角色 | 行数估算 | 新/改 |
|---|---|---|---|
| `trip-server/eval/evaluators/judge.ts` | Evaluator 入口，编排 LLM 调用 + 4 维拆分（**特殊：返回 `Record<string, EvalResult>`，4 个 key**） | ~80 | 新 |
| `trip-server/eval/judgeClient.ts` | LLM 调用封装（重试/超时/模型选择） | ~120 | 新 |
| `trip-server/eval/judgePrompt.ts` | 提示词模板（system + user builder） | ~150 | 新 |
| `trip-server/eval/judgeCache.ts` | LRU + 文件持久化缓存 | ~80 | 新 |
| `trip-server/eval/__tests__/judge.test.ts` | 单元测试（与 `evaluators.test.ts` 同级） | ~150 | 新 |
| `trip-server/eval/registry.ts` | 注册 `llm_judge` 入口 | +3 | 改 |
| `trip-server/eval/runner.ts` | 检测 `LLM_JUDGE=1` 时调 judge | +20 | 改 |
| `trip-server/eval/run.ts` | CLI `--judge` flag | +5 | 改 |
| `trip-server/eval/types.ts` | 新增 `JudgeResult` 等类型 | +40 | 改 |
| `trip-server/.gitignore` | 忽略 `.eval-judge-cache/` | +1 | 改 |
| `.github/workflows/eval.yml` | nightly 跑 `--judge` | +5 | 改 |

总计：**~580 行新代码 + ~70 行改动**。

### 3.3 启用控制

| 场景 | `LLM_JUDGE` | `JUDGE_API_KEY` | 行为 |
|---|---|---|---|
| PR 推送（默认） | 未设 | — | judge 不跑，PR gate 仅基于规则 evaluator |
| 本地手动 | `LLM_JUDGE=1` | 已设 | judge 跑，输出多维分数 |
| Nightly | `LLM_JUDGE=1` | GitHub Secrets | judge 跑，存档报告 |
| 缺 key | `LLM_JUDGE=1` | 未设 | 4 维全 fail，reason=`judge_disabled` |

## 4. 评分维度

### 4.1 4 个固定维度

| 维度键 | 中文 | 评估内容 | 1 分定义 | 5 分定义 |
|---|---|---|---|---|
| `day_by_day_feasibility` | 行程可行性 | 单日活动的时间/距离/节奏 | 单日活动 > 6 个或时间/距离冲突明显 | 节奏舒适、交通合理、有缓冲时间 |
| `constraint_adherence` | 约束遵循 | 用户明确约束（宠物/饮食/天气/儿童/预算） | 忽略用户明确约束 | 主动规避 + 提供注意事项 |
| `readability` | 表达可读性 | 文字通顺度 + 信息密度 | 信息错乱 / 关键信息缺失 / 大段重复 | 文字通顺、信息密度合适 |
| `personalization` | 个性化 | 推荐与用户偏好的契合度 | 推荐与用户偏好无关 | 明显体现用户偏好、惊喜点 |

### 4.2 证据引用规范

每个维度必须包含至少 1 条 `evidence`（直接引用 agent 输出原文 ≤ 80 字）。这是 LLM judge 设计的核心约束 —— 没有 evidence 的分数不可信。

**示例**：

```json
{
  "day_by_day_feasibility": 4,
  "evidence": "Day2 上午从宽窄巷子到锦里 1.2km，30min 即可"
}
```

**反例**（无 evidence，不应出现）：

```json
{
  "day_by_day_feasibility": 4
}
```

### 4.3 0 分特殊处理

如果 agent 输出无内容可评（如反例 fixture：用户问 Python 问题，agent 应拒答），所有维度打 0 分并 evidence 注明 `"no itinerary produced"`。这样反例 fixture 不会因为"产出空"得低分失真。

## 5. 提示词设计

### 5.1 System Prompt（**静态**，跨 fixture 复用）

```
你是行程质量评审员。基于"用户输入"和"agent 输出"，从 4 个维度评分。每个维度 1-5 分：
- 1 = 严重问题（明显违反要求 / 不可用）
- 2 = 有明显缺陷
- 3 = 合格（无大问题但无亮点）
- 4 = 良好（有亮点）
- 5 = 优秀（明显优于平均）

每个维度必须引用 agent 输出中的具体片段（≤ 80 字）作为 evidence，不接受泛泛而谈。
如果 agent 输出无内容可评（如非行程问题被正确拒答），所有维度打 0 分并 evidence 注明
"no itinerary produced"。

输出严格的 JSON（不要 ```json ``` 包装，不要任何额外文字）：
{
  "dimensions": {
    "day_by_day_feasibility": { "score": 1-5, "evidence": "..." },
    "constraint_adherence": { "score": 1-5, "evidence": "..." },
    "readability": { "score": 1-5, "evidence": "..." },
    "personalization": { "score": 1-5, "evidence": "..." }
  },
  "overall_comment": "≤ 200 字总结"
}
```

**为什么 system 静态**：跨 fixture 复用，理论上 OpenAI/Claude 端可做 prefix 缓存（不依赖 DeepSeek 的 prompt cache）。

### 5.2 User Message（**动态**）

```
[用户输入]
message: "{fixture.input.message}"
preferences: { ... }
history:
  - role: user, content: "..."
  - role: assistant, content: "..."
  - ...

[agent 输出]
text:
{output.text（截断到 8000 字符，超出截断并标注 "..."）}

json (如可解析):
{output.json 的结构化摘要}
```

**截断策略**：agent 输出超过 8000 字符时截断，避免 judge 上下文超限；截断位置在 day 边界（按 `\n## Day` 切），优先保留头尾各 4000 字。

## 6. Judge 客户端

### 6.1 接口

```ts
// eval/judgeClient.ts
export interface JudgeInput {
  fixture: Fixture
  agentOutput: AgentOutput
  systemPrompt: string
  userMessage: string
}

export interface JudgeResult {
  dimensions: Record<DimensionKey, { score: number; evidence: string }>
  overallComment: string
  raw: string            // LLM 原始响应，调试用
  model: string          // 实际调用的模型 ID
  usage?: { prompt: number; completion: number; total: number }
  latencyMs: number
}

export interface JudgeClient {
  evaluate(input: JudgeInput): Promise<JudgeResult>
}
```

### 6.2 实现

- **协议**：OpenAI 兼容 Chat Completions API（GPT-4.1 / Claude Sonnet 4 都支持）
- **环境变量**：
  - `JUDGE_API_KEY`：API key
  - `JUDGE_BASE_URL`：默认 `https://api.openai.com/v1`，Claude 改 `https://api.anthropic.com/v1`
  - `JUDGE_MODEL`：默认 `gpt-4.1`
- **超时**：30s
- **重试**：2 次，指数退避 1s / 2s
- **解析失败**：抛 `JudgeParseError`，由 evaluator 转 4 维 fail
- **网络错误**：抛 `JudgeNetworkError`，由 evaluator 转 4 维 fail

### 6.3 不做的

- **不接 LangChain**：多一层抽象、调试不直观
- **不做流式**：judge 只需最终 JSON，不需要流式
- **不做 batch 调 API**：单 fixture 1 次调用足够简单

## 7. 缓存策略

### 7.1 缓存键

```
key = sha256(fixtureId + ":" + inputHash + ":" + model + ":" + systemPromptHash)
inputHash = sha256(fixture.input.message + JSON.stringify(fixture.input.preferences) + agentOutput.text + JSON.stringify(agentOutput.json))
systemPromptHash = sha256(systemPrompt)
```

**字段解释**：
- `fixtureId` — 区分不同 fixture
- `inputHash` — 同一 fixture 内，preferences / agent 输出变化时失效
- `model` — 换 judge 模型不命中旧缓存
- `systemPromptHash` — 调 prompt 措辞时不命中旧缓存（避免新旧 prompt 结果混用）

### 7.2 缓存实现

- **内存 LRU**：容量 200 entries（`Map` + 简单 LRU）
- **文件持久化**：`.eval-judge-cache/{hash}.json`，TTL 7 天
- **Git**：`.gitignore` 新增 `.eval-judge-cache/`
- **命中时机**：runner 启动时一次性加载到内存；写时同时更新内存和文件

### 7.3 缓存效果预估

| 场景 | 命中率 | 价值 |
|---|---|---|
| 同 fixture 重跑（nightly + 本地复跑） | ~100% | 节省完整 LLM 调用 |
| 跨 fixture | ~0% | input 不同必然不命中 |
| 改 system prompt 措辞 | 0% | 主动失效，避免新旧 prompt 结果混用 |
| 换 judge 模型 | 0% | 主动失效，避免跨模型结果混淆 |

## 8. Runner 集成

### 8.1 关键设计：judge 是"特殊 evaluator"

现有 13 个 evaluator 都遵循 `EvaluatorFn = (output, fixture) => EvalResult` 签名，返回**单个** `EvalResult` 并存到 `evaluatorResults[evaluatorName]`。

`llm_judge` 是**特殊**的：它返回 `Record<string, EvalResult>`（4 个 key），由 runner 拆开 merge 到 `evaluatorResults`。这样在 `byEvaluator` 聚合和 `evaluatorResults` 存储里，看到的就是 4 个独立条目，与现有结构对齐。

**存储 key 约定**：

| 用途 | 格式 | 例 |
|---|---|---|
| 存储 key（`evaluatorResults` / `byEvaluator`） | `{dimension_key}` | `day_by_day_feasibility` |
| 报告展示名 | `llm_judge.{dimension_key}` | `llm_judge.day_by_day_feasibility` |

存储层不存 `llm_judge` 本身这个 key，只存 4 个维度 key；展示层加 `llm_judge.` 前缀以表明来源。

### 8.2 runner.ts 改动

```ts
// 在 for each evaluator 循环中：
if (name === 'llm_judge' && !process.env.LLM_JUDGE) {
  // judge 关闭时：4 维全标 disabled（不阻塞其他 evaluator）
  for (const dim of DIMENSION_KEYS) {
    result[dim] = { pass: false, reason: 'judge_disabled: LLM_JUDGE not set' }
  }
  continue
}
if (name === 'llm_judge') {
  const judgeResults = await llmJudgeEvaluator(output, fixture)
  // judgeResults: Record<DimensionKey, EvalResult>，4 个 key
  Object.assign(result, judgeResults)
  continue
}
```

`llmJudgeEvaluator` 在 `eval/evaluators/judge.ts` 里实现，签名特殊（不注册到 `EVALUATORS` 表里 — 避免 runner 误以为返回单个 `EvalResult`）。

### 8.3 报告展示

`ReportSummary.byEvaluator` 展示拆维后 4 行：

```
=== 按 evaluator ===
  schema_check: 7/8 (87.5%)
  llm_judge.day_by_day_feasibility: 6/10 (60.0%)  [3.2/5 avg]
  llm_judge.constraint_adherence: 5/10 (50.0%)     [2.8/5 avg]
  llm_judge.readability: 9/10 (90.0%)             [4.1/5 avg]
  llm_judge.personalization: 7/10 (70.0%)         [3.5/5 avg]
```

**JSON 报告存档**（`eval-reports/...json`）保留完整结构（4 个独立 entry，共享同一 `details.dimensions` 引用）：

```json
{
  "day_by_day_feasibility": {
    "pass": true,
    "details": {
      "score": 4,
      "evidence": "Day2 上午从宽窄巷子到锦里 1.2km，30min 即可",
      "_sharedDimensions": {
        "day_by_day_feasibility": { "score": 4, "evidence": "..." },
        "constraint_adherence": { "score": 3, "evidence": "..." },
        "readability": { "score": 5, "evidence": "..." },
        "personalization": { "score": 4, "evidence": "..." },
        "overall_comment": "...",
        "model": "gpt-4.1",
        "latencyMs": 4200
      }
    }
  },
  "constraint_adherence": { "pass": false, "details": { "score": 2, "evidence": "...", "_sharedDimensions": "..." } },
  "readability": { ... },
  "personalization": { ... }
}
```

每个 entry 的 `details._sharedDimensions` 引用同一份完整 judge 响应（节省存档空间，避免 4 份重复 evidence）。每个 entry 的 `details.score` / `details.evidence` 是该维的扁平视图，方便按维快速过滤。

## 9. 错误处理

| 场景 | 行为 | 原因 |
|---|---|---|
| `JUDGE_API_KEY` 缺失 | 4 维全 fail，reason=`judge_disabled: JUDGE_API_KEY not set` | 不影响其他 evaluator |
| LLM 返回非 JSON | 4 维全 fail，reason=`judge_parse_error: <line>:<col> <msg>` | 重试 2 次后仍失败 |
| LLM 返回 JSON 但缺字段 | 该维 fail，其他维正常 | 容错 |
| 维度 score 越界（< 0 或 > 5） | 该维 fail，reason=`score_out_of_range` | 容错 |
| 30s 超时 | 4 维全 fail，reason=`judge_timeout` | 重试 2 次后仍超时 |
| 网络错误 | 4 维全 fail，reason=`judge_network_error` | 重试 2 次后仍失败 |

**核心原则**：LLM judge 失败**绝不阻塞**其他 evaluator，也不影响 fixture 整体 pass（PR gate 不依赖 judge）。

## 10. 校准流程

### 10.1 Gold Set 创建

- **第一周**（实施后立即）：选 20-30 个真实 case
  - 覆盖 4 个 fixture 类别（典型/约束/多轮/反例）
  - 来源：nightly 报告中的真实 agent 输出
- **打标者**：1 个 author（你）独立打标 4 个维度（1-5 分）
- **时间预算**：~2-3 小时
- **存储**：`docs/eval-calibration/gold-set-2026-07.json`（gitignored，避免污染 repo）

### 10.2 一致性指标

- **指标**：Cohen's Kappa（author vs judge），per 维度计算
- **目标**：Kappa ≥ 0.6（substantial agreement）
- **低于 0.6**：调整 prompt 措辞，常见手段：
  - 加 few-shot examples
  - 修改维度定义（更明确边界 case）
  - 调整 system prompt 的语气
- **工具**：Python `sklearn.metrics.cohen_kappa_score`（独立脚本，不进 eval 框架）

### 10.3 校准报告

`docs/eval-calibration-2026-07.md`（不 gitignore，进 repo 记录过程）：

```markdown
# 校准报告 — 2026-07-XX

## 概况
- 20 case × 4 维度 = 80 对比
- judge 模型: gpt-4.1
- author: wang

## 整体 Kappa
0.71 (substantial)

## per 维度 Kappa
| 维度 | Kappa | 解释 |
|---|---|---|
| day_by_day_feasibility | 0.78 | 高度一致 |
| constraint_adherence | 0.62 | 一致，少数边界 case |
| readability | 0.55 | borderline，prompt 待调 |
| personalization | 0.69 | 一致 |

## 不一致 case (readability < 4)
- fixture: chengdu-3days
- author: 4 / judge: 2
- 原因：author 认为"信息密度合适"，judge 误判"模板化"
- 调 prompt 方向：readability 维度增加"信息密度"明确说明
```

### 10.4 持续校准

- 调 prompt 后必跑 gold set
- 每月追加 5-10 个新 case 到 gold set
- 长期目标：gold set 50+ case

## 11. CI 集成

### 11.1 触发矩阵

| 触发 | LLM judge | JUDGE_API_KEY | 原因 |
|---|---|---|---||
| PR 推送 | 关闭 | 不需要 | 控成本 + PR gate 简单 |
| main 推送 | 关闭 | 不需要 | 同上 |
| Nightly (02:00 UTC) | **开启** | GitHub Secrets | 跑真实 judge，存档报告 |
| 本地手动 | `LLM_JUDGE=1` | 本地 `.env` | 调 prompt 后必跑 |

### 11.2 Nightly 配置

``.github/workflows/eval.yml` 改动：

```yaml
nightly-eval:
  if: github.event_name == 'schedule'
  env:
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    JUDGE_API_KEY: ${{ secrets.JUDGE_API_KEY }}
    LLM_JUDGE: '1'
  steps:
    - run: npm run eval:real -- --samples 1 --judge
```

### 11.3 报告存档

Nightly 报告上传 GitHub Actions artifacts，保留 90 天：

```
eval-reports/2026-07-02_02-00-00_real_s1.json
eval-reports/2026-07-02_02-00-00_real_s1_judge.json  # 新增
```

## 12. 测试策略

### 12.1 单元测试

| 文件 | 覆盖 |
|---|---|
| `judgeClient.test.ts` | mock OpenAI 客户端：prompt 构造、JSON 解析、重试（成功/失败/超时）、usage 提取 |
| `judgeCache.test.ts` | LRU 行为、TTL 过期、文件持久化、key 计算（4 字段）、hash 稳定性 |
| `judge.test.ts`（evaluator） | mock judgeClient：4 维拆分逻辑、错误转 fail、evidence 必填校验 |

### 12.2 集成测试

- **1 个真实 fixture 端到端**（需要 `JUDGE_API_KEY`，CI 跳过，本地手动跑）
- **校验**：
  - 4 个 EvalResult 共享 `details.dimensions`
  - `byEvaluator` 正确显示 4 行
  - 缓存命中后第二次跑 < 100ms 完成 judge 部分

### 12.3 校准测试

- 调 prompt 后必跑 gold set，对比 kappa
- 校准脚本：`scripts/calibration.py`（独立，不进 eval 框架）

## 13. 实施步骤

按依赖排序：

1. **类型先行**（30 min）— `eval/types.ts` 加 `JudgeResult` / `DimensionKey` 等类型
2. **judgePrompt.ts**（1 h）— 静态 system prompt + user builder + 截断逻辑 + 单元测试
3. **judgeCache.ts**（1 h）— LRU + 文件持久化 + 4 字段 key + 单元测试
4. **judgeClient.ts**（1.5 h）— OpenAI 兼容调用 + 重试 + 解析 + 单元测试
5. **evaluators/judge.ts**（1 h）— 4 维拆分 + 错误转 fail + 单元测试
6. **接入**（1 h）— `registry.ts` / `runner.ts` / `run.ts` / `.gitignore`
7. **mock 模式端到端**（30 min）— 跑 `npm run eval -- --judge` 验证报告
8. **真实模式 1 个 fixture**（30 min）— 用真实 `JUDGE_API_KEY` 跑 1 个 fixture 看完整数据流
9. **Gold set 准备**（2-3 h）— 20 case 打标
10. **校准**（1 h）— 跑校准脚本，调 prompt 直至 Kappa ≥ 0.6
11. **CI 接入**（30 min）— `.github/workflows/eval.yml` nightly 加 `--judge`

**总计**：~10-12 小时（约 1.5-2 个工作日）。

## 14. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| GPT-4.1 评分波动 | 同 itinerary 多次跑结果不一致 | 默认 1 采样 + 报告存档便于追溯；多采样不默认开启 |
| 4 维 prompt 耦合 | 单次 LLM 失败 → 4 维全挂 | 错误转 fail 不阻塞其他 evaluator；PR gate 不依赖 judge |
| 校准数据少（20 case） | Kappa 估计不稳定 | 20 case 是 minimum，持续追加到 50+ |
| LLM 上传 prompt 数据 | 用户输入发到 OpenAI/Claude | OpenAI/Claude API 默认不训练用户数据（需查具体 ToS）；如要 100% 隔离需选自部署模型（已排除） |
| Token 成本失控 | nightly $30/天 不可接受 | 缓存 + 默认 1 采样 + 监控 `JUDGE_USAGE` env；预算上限可配 |
| judge 与 agent 同模型 | 自我打分偏差 | 已选 GPT-4.1 / Claude（与 agent 用的 DeepSeek 不同） |
| 反例 fixture 失真 | "拒答"被打低分 | §4.3 0 分特殊处理 |

## 15. 开放问题（实施时确认）

- [ ] **默认 judge 模型**：先 GPT-4.1，可改 `JUDGE_MODEL` env
- [ ] **是否需要 few-shot examples**：建议先 0-shot 测 baseline，再决定
- [ ] **Gold set 公开到 repo**：建议 gitignored，本地文件
- [ ] **多采样策略**：默认 1 次；用户改 `--samples 3` 时 judge 跑 3 次取均分
- [ ] **judge 评 0 分是否算 fixture fail**：默认**不算**（与"不阻塞其他 evaluator"一致）

## 16. 附录

### 16.1 关键文件引用

| 引用 | 路径 |
|---|---|
| 现有 eval 框架说明 | `docs/agent-eval.md` |
| EvalResult 类型（details 字段已留位） | `trip-server/eval/types.ts:106-113` |
| ReportSummary 类型（byEvaluator 已支持） | `trip-server/eval/types.ts:131-142` |
| 注册表模式参考 | `trip-server/eval/registry.ts` |
| 通用 evaluator 实现参考 | `trip-server/eval/evaluators/general.ts` |

### 16.2 命名约定

- **Evaluator 键名**：`llm_judge`（registry 注册名）
- **报告展示名**：`llm_judge.{dimension_key}` 形式
- **文件命名**：`judge.ts` / `judgeClient.ts` / `judgePrompt.ts` / `judgeCache.ts`（保持一致前缀）

### 16.3 Token 成本预估

- System prompt：~350 tokens（静态）
- User message：~1500-3000 tokens（fixture + agent 输出）
- 输出：~500-1000 tokens（4 维 + evidence + comment）
- 单 fixture 单次：~2500-4500 tokens
- 10 fixture 单次跑：~25k-45k tokens
- GPT-4.1 价格：$2.5/M input + $10/M output
- 单次跑成本：~$0.15-0.40
- 缓存命中后：~$0
- Nightly 1 次/月成本：~$5-12（按 30 天算）
