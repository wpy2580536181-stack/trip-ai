# Agent 评估体系

> 实现位置：`trip-server/eval/`
> 跑测试：`npm test`（单元测试）
> 跑评估：`npm run eval`（mock）/ `npm run eval:real`（真实）
> 类型检查：`npm run eval:typecheck`
> CI：`.github/workflows/eval.yml`（PR 必跑 mock + typecheck；nightly 跑真实）

---

## 1. 目标

把"agent 改完不知道好坏"变成数据驱动的质量门：
- 改 system prompt / 调权重 / 换 LLM 之前 → 跑 5 分钟 eval
- 看到 pass rate 变好/变差 → 决定是否保留改动
- 线上出问题时 → 加 fixture → 修 agent → 跑 eval 验证

## 2. 真实生产数据

截至 2026-06-21，**单采样 50-70% / 三采样多数 60-70% 通过**：

| Fixture | 类型 | 通过率 |
|---|---|---|
| chengdu-3days-foodie-relaxed | 典型 | 100% |
| xian-2days-family-kid | 典型 | 90% |
| multi-turn-destination-change | 多轮 | 100% |
| non-travel-question-refused | 反例 | 100% |
| multi-turn-detail-question | 多轮 | 70% |
| rejection-no-trip-output | 反例 | 60% |
| hangzhou-2days-rainy-day | 约束 | 70% |
| beijing-3days-halal-vegetarian | 约束 | 60% |
| shanghai-2days-with-pet | 约束 | 50% |
| tokyo-5days-budget-tight | 典型 | 0% (fixture 期望过严) |

截至 2026-06-28，**DeepSeek prompt cache 命中率 82-89%，累计 85.1%**（5 fixture 抽样，详见 §12.5）。

LLM 波动不可避免。**重要规则**：改完 agent 跑 3 次，多数决定去留。

## 3. 架构

```
fixtures/*.yaml          静态测试用例（10 个）
   ↓ loadFixtures()
runner.ts                 加载 + 调度
   ↓ runFixture()
agentFn / mockAgent       调真实 LLM 或 mock
   ↓
evaluators/*.ts           13 个评分函数
   ↓
report                    按 tag / evaluator 维度汇总
```

## 4. Fixture 设计

10 个 fixture 覆盖 4 类场景：

| # | 场景 | 类别 |
|---|---|---|
| 1 | 成都 3 天 美食慢节奏 | 典型 |
| 2 | 东京 5 天 学生穷游 | 典型 |
| 3 | 西安 2 天 亲子 6 岁 | 典型 |
| 4 | 多轮 改目的地（成都→重庆） | 多轮 |
| 5 | 用户没决定去哪 | 反例 |
| 6 | 上海 2 天 带金毛 | 约束 |
| 7 | 北京 3 天 清真 | 约束 |
| 8 | 杭州 2 天 雨天 | 约束 |
| 9 | Python 编程问题 | 反例 |
| 10 | 多轮 追问 Day 2 细节 | 多轮 |

### Fixture YAML 结构

```yaml
id: chengdu-3days-foodie-relaxed
description: 成都 3 天慢节奏美食之旅
tags: [smoke, chengdu, food, relaxed]

input:
  message: "带父母去成都玩 3 天..."
  preferences: { travelStyle: relaxed, pace: slow, interests: [美食, 文化] }
  history: []

expected:
  # 必含 POI（name_contains 模糊 + city 可选 + 100km 周边放宽）
  must_contain_pois:
    - { name_contains: "宽窄巷子", city: "成都" }
  # 必含关键词
  must_contain_keywords: [火锅, 茶馆]
  # 必不含关键词
  must_not_contain_keywords: [酒吧, 蹦极]
  # 结构断言
  days: 3
  json_valid: true
  max_activities_per_day: 4
  # 工具调用规则
  tool_calls:
    - { name: "retrieve_knowledge", min_calls: 1 }

evaluators: [schema_check, poi_city_match, keyword_coverage, ...]
```

## 5. Evaluator 列表

| 名称 | 类别 | 验证什么 |
|---|---|---|
| `schema_check` | 通用 | JSON 解析 + 严格 zod schema |
| `poi_city_match` | 通用 | POI 出现在文本/JSON + 城市 + 100km 周边 |
| `keyword_coverage` | 通用 | 必含/必不含关键词 |
| `tool_call_audit` | 通用 | 工具调用 min/max 次数 |
| `pace_consistency` | 通用 | 天数 + 每天活动数 |
| `pet_constraint_check` | 领域 | 宠物禁入场所 + 注意事项 |
| `dietary_constraint_check` | 领域 | 饮食禁忌（清真/素食/无麸质） |
| `weather_adaptation_check` | 领域 | 天气查询 + 室内调整 |
| `budget_field_present` | 领域 | 每时段 ticket 含价格 |
| `kid_friendly_check` | 领域 | 儿童不宜 + 亲子提示 |
| `destination_override` | 多轮 | 跟随最新目的地指令 |
| `context_memory` | 多轮 | 记得上文关键信息 |
| `no_forced_itinerary` | 反例 | 不该硬塞具体行程 |

## 6. 周边城市判定（100km）

`eval/geo.ts` 维护了 ~50 个城市坐标 + Haversine 距离计算。
判定规则：**直线距离 ≤ 100km 视为周边**。

示例：
- 都江堰 → 成都（50km）✓
- 峨眉山 → 成都（140km）✗
- 苏州 → 上海（85km）✓
- 镰仓 → 东京（50km）✓

> 注：成都/西安等内陆旅游城市的"100km 周边"通常没热门城市，
> 长安到华山 120km 不算周边——按真实地理划分。

## 7. 使用

### 6.1 跑全部 fixture

```bash
npm run eval
```

输出示例：
```
=== Trip Agent Eval ===
fixtures: trip-server/eval/fixtures/trip-planning
mode: MOCK agent
registered evaluators: 13 (schema_check, poi_city_match, ...)

将跑 10/10 个 fixture

[chengdu-3days-foodie-relaxed] 成都 3 天慢节奏美食之旅
  ✓ 4ms

...

=== 汇总 ===
5/10 通过 (50.0%)  2ms

按 evaluator:
  7/8      schema_check
  6/7      poi_city_match
  6/9      keyword_coverage
  ...
```

### 6.2 跑指定 fixture

```bash
npm run eval -- --id 001-chengdu-3days-foodie-relaxed
npm run eval -- --tag multi-turn
```

### 6.3 跑真实 agent

需要先实现 `buildRealAgent`（见 `eval/run.ts` 里的 TODO）：
1. 后端服务运行在 localhost:3000
2. 调 `/api/trip/chat` 流式接口
3. 收集 SSE 事件 → AgentOutput
4. 退出码 0/1 表示通过/失败

```bash
npm run eval:real
```

## 8. 添加新 fixture

```yaml
# fixtures/trip-planning/011-my-new-test.yaml
id: my-new-test
description: 简短描述
tags: [xxx]   # 用于按 tag 过滤

input:
  message: "用户问题"
  preferences: { ... }
  history: []  # 多轮时填

expected:
  must_contain_pois: [...]
  must_contain_keywords: [...]
  must_not_contain_keywords: [...]
  days: 3
  json_valid: true
  tool_calls: [...]
  # 任何 other 字段可加，evaluator 通过 fixture.expected 取

evaluators: [schema_check, ...]
```

## 9. 添加新 evaluator

1. 在 `eval/evaluators/{general,domain,multi-turn}.ts` 加函数
2. 函数签名 `(output: AgentOutput, fixture: Fixture) => EvalResult`
3. 在 `eval/registry.ts` 注册
4. 在 `eval/__tests__/evaluators.test.ts` 写正/反两路测试
5. 跑 `npx vitest run eval/__tests__/evaluators.test.ts` 验证
6. 跑 `npm run eval:typecheck` 验证类型

## 10. 单元测试

```bash
npx vitest run eval/__tests__/evaluators.test.ts
```

53 个测试覆盖：
- 每个 evaluator 至少 1 正 1 反
- 边界条件（空字符串、缺字段、未注册城市）
- 集成（schema + 周边城市 + 跨 evaluator 协作）

## 11. 扩展路线

### MVP（已交付）
- ✅ 10 fixture + 13 evaluator
- ✅ mock agent 跑通闭环
- ✅ 单元测试 56 个全过
- ✅ TypeScript 严格类型
- ✅ **真实 agent 接入**（HTTP 调 /api/trip/chat + SSE 解析 + 重试）
- ✅ **CI 集成**（GitHub Actions：PR 跑 mock + typecheck，nightly 跑真实）
- ✅ **多采样多数投票**（`--samples 3`，抗 LLM 波动）
- ✅ **报告存档**（`eval-reports/YYYY-MM-DD_HH-MM-SS_*.json`）

### 第二阶段
- ✅ 接入 DeepSeek/AGNES 真实模型（5-7/10 pass）
- ✅ 收集 token 用量 / 响应时长（chat path `complete.usage` 字段 + recommend path 同步补齐）
- ✅ 缓存命中率（cache_read 在 tokenTracker / SSE / eval 3 处埋点全部贯通，见 §12.5）

### 第三阶段
- ⏳ LLM-as-Judge（用 GPT-4 给 5 分制打分）
- ⏳ 校准 judge 评分（人评 20 个 case 对比）
- ⏳ 在线反馈按钮 + 收集

### 第四阶段
- ⏳ 接入 LangSmith / LangFuse
- ⏳ 自动 trace 每次 agent 执行

## 12. 多采样 / 报告 / CI

### 12.1 多采样多数投票

LLM 行为有波动（同一问题不同时间答案可能不同）。改完 agent 跑 3 次取多数：

```bash
EVAL_DELAY_MS=5000 npm run eval:real -- --samples 3
```

实现：`runner.ts` 的 `samples` 参数。evaluator 在每个 sample 上跑一遍，**多数**决定 pass/fail。
报告里 `details: { passCount, totalSamples, perSample }` 可看具体每次结果。

**token 成本**：3 采样 = 3 倍 token。注意 token budget 限制（5万/小时）。
建议：单采样先看，3 采样用于 PR/release 决策。

### 12.2 报告存档

```bash
EVAL_SAVE=1 npm run eval:real              # 保存到 eval-reports/
EVAL_SAVE=1 npm run eval:real -- --samples 3
```

文件格式 `eval-reports/YYYY-MM-DD_HH-MM-SS_{real|mock}_s{N}.json`。
详见 `eval-reports/README.md`（jq 查历史 pass rate、最常失败 fixture）。

### 12.3 CI 集成

`.github/workflows/eval.yml`：

- **PR + main 推送**：跑 `tsc --noEmit` + `tsc eval:typecheck` + `vitest` + `npm run eval`（mock）
- **每周日 02:00 UTC**：nightly 跑真实 eval（需 secrets `DEEPSEEK_API_KEY`）
- **失败阻塞 merge**：mock eval 失败 → PR 红 ×
- **report artifact**：nightly 报告上传 GitHub Actions，保留 90 天

### 12.4 修过的真实问题（2026-06-21）

跑真实 eval 暴露的 4 个真实 bug：

1. **hangzhou-rainy 不调 getWeather** — systemPrompt 加"用户提天气必须调 get_weather"
2. **beijing-halal "无猪肉" 被误判** — evaluator 加"避免语境"识别（"无/不/避免/已排除"前后文）
3. **shanghai-pet 推美术馆** — systemPrompt 加"宠物避雷"提示
4. **工具名大小写不匹配**（getWeather vs get_weather）— toolCallAudit 改大小写不敏感

### 12.5 缓存命中率（Cache Hit Rate）

**指标**：`hitRate = prompt_cache_hit_tokens / prompt_tokens`，反映 DeepSeek prompt cache 复用率。直
接影响单次请求成本（缓存命中的 token 按 DeepSeek 折扣价计费）。

**基线**（2026-06-28，5 fixture 抽样，sample=1）：

| Fixture | prompt | cached | hitRate |
|---|---|---|---|
| chengdu-3days-foodie-relaxed | 7,635 | 6,272 | 82.1% |
| tokyo-5days-budget-tight | 3,753 | 3,328 | 88.7% |
| xian-2days-family-kid | 15,436 | 13,184 | 85.4% |
| beijing-3days-halal-vegetarian | 18,087 | 15,104 | 83.5% |
| hangzhou-2days-rainy-day | 16,295 | 14,208 | 87.2% |
| **累计** | **61,206** | **52,096** | **85.1%** |

**完整数据流**（修过 3 个 bug 后贯通）：

```
LLM response
  ↓ usage_metadata.input_token_details.cache_read
    或 response_metadata.usage.prompt_tokens_details.cached_tokens
planner.ts / chatGraph.ts / chatPlanner.ts: extractUsageFromResult
  ↓ usage.cached 累加
AgentEngine: onEvent({ type: 'complete', content, usage })
  ↓ 序列化 SSE
前端 + eval real-agent.ts: parseSSE
  ↓ AgentOutput.tokens.cached
runner.ts: tokensAgg.cached 累加 → summary.totalTokens.hitRate
  ↓ 打印
run.ts: 'Cache: cached=X hitRate=Y%' (≥50% 绿 / ≥30% 黄 / <30% 红)
```

**修过的 3 个 bug**（commit `062955e`，2026-06-28）：

1. `tokenTracker.onLLMEnd` 没读 `promptTokensDetails.cachedTokens` → `tokenUsageLog.cached` 永远 0，
   admin dashboard "缓存命中率"看板失效
2. recommend 路径的 SSE `complete` 事件漏 `usage` 字段（chat 路径有）→ `message.metadata.usage.cached`
   永远 0
3. eval 框架：
   - `types.ts` `AgentOutput.tokens` / `ReportSummary.totalTokens` 缺 `cached` 字段
   - `real-agent.ts parseSSE` 从 `event.data.usage` 读，但 SSE 序列化在 `event.usage` 顶层（兼容双路径）
   - `run.ts` 不打印 hitRate

**怎么读**：

- 改 prompt 结构（增减 system 字段、调整顺序）→ 跑 eval 看 hitRate 变没变
- 改 system prompt 加动态内容 → hitRate 应该下降（动态部分无法被 prefix 缓存）
- 同 fixture 重复跑 → 第 2 次起 hitRate 应该 > 首次（warm cache）
- hitRate 长期 < 50% → 考虑把动态内容挪到 user message 或加 cache breakpoint

**怎么跑**：

```bash
# 单采样
npm run eval:real -- --id chengdu-3days-foodie-relaxed
# 多 fixture 对比
npm run eval:real -- --tag smoke --tag chengdu --tag tokyo
# 看完整 hitRate 分布
EVAL_PROGRESS_LOG=/tmp/eval-progress.log npm run eval:real -- --samples 1
tail -f /tmp/eval-progress.log   # 实时看每个 fixture 的 hitRate
```

## 13. 文件清单

| 文件 | 作用 |
|---|---|
| `eval/types.ts` | 类型定义（Fixture/EvalResult/AgentOutput） |
| `eval/geo.ts` | 50 个城市坐标 + 100km 周边判定 |
| `eval/registry.ts` | 13 个 evaluator 注册表 |
| `eval/runner.ts` | fixture 加载 + 跑全部 + 汇总 |
| `eval/run.ts` | CLI 入口（支持 --id / --tag / --real） |
| `eval/evaluators/general.ts` | 5 个通用 evaluator |
| `eval/evaluators/domain.ts` | 5 个领域 evaluator |
| `eval/evaluators/multi-turn.ts` | 3 个多轮/反例 evaluator |
| `eval/__tests__/evaluators.test.ts` | 53 个单元测试 |
| `eval/fixtures/trip-planning/*.yaml` | 10 个 fixture |
| `tsconfig.eval.json` | eval 独立 tsconfig |
| `package.json` | + eval / eval:real / eval:typecheck scripts |

总计 **13 个 TypeScript 文件 + 10 个 YAML**，约 1000 行新代码。
