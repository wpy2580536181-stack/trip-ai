# Agent 架构重构设计

> 2026-06-27 · 从单 Agent 换成 LangGraph 状态图：researcher（零 LLM、确定性并行 fan-out）+ planner（零工具、纯生成）两段式流水线，chat 加路由判断。

## 背景

当前 `AgentEngine`（`trip-server/src/services/agent/agentEngine.ts`）是单一 `AgentExecutor`，4 个工具全挂在一个 agent 上。LLM 自主决定何时调哪个工具——问题：

1. `recommend` 场景下 LLM 经常漏调工具或重复查询，行程质量不稳定
2. 单 agent 既负责情报收集又负责结构化生成，prompt 膨胀（`systemPrompt.ts` 已 123 行）
3. 无法并行调工具（LLM 串行 thought→action→observation）
4. `agent-improvements.md` 3.1（LangGraph）+ 3.2（多 Agent）已埋伏笔，本次落地

## 目标

- `recommend()`：research → planner 两段式流水线，research 阶段零 LLM、确定性并行 fan-out 全部 4 个工具，planner 阶段零工具、纯 JSON 生成
- `chat()`：加规则式路由——规划类问题（含天数 + 规划关键词）走新流水线（planner 输出 markdown 流式），闲聊/单点查询走原单 agent 不动
- 对外契约不变：`AgentEngine.chat()` / `AgentEngine.recommend()` 签名、`AgentStreamEvent` 类型、`TraceRecorder` + `messageId` FK、token usage 追踪、fallback 机制、`tripService.ts` 调用方全部不改

## 非目标（YAGNI）

- 不引入 LLM 路由分类器（规则式够用，后续可升级）
- 不拆 4 个独立 agent（天气/距离是工具不是 agent，景点/酒店底层共享 `searchSpots`）
- 不改 DB schema（AgentStep 表结构不变）
- 不重构 `systemPrompt.ts`（legacy agent 用的 prompt 不动，新增 planner 专用 prompt）
- 不动前端（SSE 事件类型不变）

## 架构

### 总体

```
recommend():  START → research → planner → [validate] ──valid──→ END
                                              │
                                           invalid
                                              ↓
                                         retry_planner → END

chat():       START → router ──planning──→ research → chat_planner → END
                       │
                    general
                       ↓
                 legacy_agent（现有 AgentExecutor + 4 工具，不动）→ END
```

### 状态结构

LangGraph `StateGraph`，状态用 `Annotation.Root`：

```typescript
import { Annotation } from '@langchain/langgraph'
import type { BaseMessage } from '@langchain/core/messages'
import type { TripContent, TokenUsage } from '../../../types/agent'

export const PlannerState = Annotation.Root({
  // 输入
  userId: Annotation<number>,
  message: Annotation<string>,
  city: Annotation<string>,
  budget: Annotation<number | undefined>,
  days: Annotation<number | undefined>,
  departureCity: Annotation<string | undefined>,
  userPreferences: Annotation<Record<string, any> | null | undefined>,
  conversationHistory: Annotation<BaseMessage[]>,
  // research 产出
  researchBundle: Annotation<{
    attractions?: string
    food?: string
    hotels?: string
    weather?: string
    distance?: string
  }>,
  // planner 产出
  rawOutput: Annotation<string | undefined>,
  parsed: Annotation<TripContent | undefined>,
  // 元数据
  usage: Annotation<TokenUsage>,
  route: Annotation<'planning' | 'general' | undefined>,
  errors: Annotation<string[]>,
})
```

非可变对象（`TraceRecorder`、`onEvent`、`signal`、LLM 实例）通过 `config.configurable` 注入，不进 state。

### 节点

#### research（确定性 fan-out，零 LLM）

根据 `city` / `departureCity` / `userPreferences` 用模板拼查询词，`Promise.allSettled` 并行调全部 4 个工具：

| 工具 | 查询词模板 | 条件 |
|---|---|---|
| `retrieveKnowledgeTool` (attraction) | `${city} 必去 景点 ${interests}` | 总是 |
| `retrieveKnowledgeTool` (food) | `${city} 美食 推荐 ${interests}` | 总是 |
| `searchHotelsTool` | `{ city, budget: budget/days/1.5 }` | 总是 |
| `getWeatherTool` | `{ city }` | 总是 |
| `calculateDistanceTool` | `{ from: departureCity, to: city }` | 有 `departureCity` 才查 |

- `interests` = `userPreferences.interests?.join('') ?? ''`
- 酒店单晚预算 = `budget / days / 1.5`（经验系数，住宿通常占总预算 ~40%）
- `Promise.allSettled` 容错：单个工具失败用 fallback 文案填充 bundle，planner 照常工作
- 每个工具调用前后 emit `tool_start` / `tool_end` 事件 + `traceRecorder.add()`
- step 编号由节点内 `stepCounter` 维护（通过 `configurable` 传入）

#### planner（recommend 模式，零工具，纯 JSON 生成）

- 系统 prompt = 新建 `buildPlannerPrompt(state)`，含 research bundle 全文注入 + 现有 `buildRecommendSystemPrompt` 的 JSON 规范部分
- prompt 明确："以下是已检索的真实数据，基于此生成 JSON，不要再调用工具"
- 调 `invokeLLMWithFallback()`（非流式，因为要 Zod 校验整段）
- `validateOutput` 条件边：`TripContentSchema.parse(extractJson(rawOutput))`，失败走 `retry_planner`（现有重试逻辑搬迁）

#### chat_planner（chat 规划模式，零工具，markdown 流式）

- 系统 prompt = 新建 `buildChatPlannerPrompt(state)`，含 research bundle + markdown 输出指令
- 流式调用，逐 token emit `chunk` 事件
- 复用 `processStream` 的 token 提取逻辑

#### router（chat 路由，纯规则零 LLM）

```typescript
const PLANNING_KEYWORDS = ['规划', '行程', '几日游', '攻略', '安排', '路线', '帮我计划', '怎么玩']
const DAYS_PATTERN = /\d+\s*日|几天|多少天/

function isPlanningRequest(message: string): boolean {
  return PLANNING_KEYWORDS.some(kw => message.includes(kw)) && DAYS_PATTERN.test(message)
}
```

- "帮我规划北京三日游" → planning → research → chat_planner
- "北京今天天气怎么样" → general → legacy_agent
- "成都有什么好吃的" → general → legacy_agent

#### legacy_agent（现有 AgentExecutor，不动）

chat 的 general 分支保留现有 `buildAgent()` + 4 工具 + `processStream()`，零改动。

### validate + retry（recommend 模式）

复用现有 `agentEngine.ts:374-407` 的 Zod 校验 + 重试逻辑：

- `validateOutput` 节点：`TripContentSchema.parse(extractJson(state.rawOutput))`
- 失败 → `retry_planner` 节点：拼重试 prompt（含 zod 错误信息 + JSON 规范提醒），再调一次 planner
- 再失败 → 抛错（同现有逻辑）

### 现有机制适配

| 机制 | 接入方式 |
|---|---|
| `TraceRecorder` + `messageId` FK | `config.configurable.traceRecorder`，节点内 `add()`，graph 结束后 `flush()` |
| `AgentStreamEvent` / `onEvent` | `config.configurable.onEvent`，节点内 emit |
| `signal` (AbortSignal) | `config.configurable.signal`，传给 `graph.streamEvents(input, { signal })` |
| token usage 累计 | planner/chatPlanner 节点内 `on_chat_model_end` 事件累计，写入 `state.usage` |
| fallback LLM | planner/chatPlanner 节点内 catch 后 `createLLMFromConfig(fallbackLLMConfig)` 重试 |
| `withToolCache` | research 节点调用的是已包好 `withToolCache` + `withResilience` 的工具实例，零改动 |
| `ToolCache` 实例 | `AgentEngine.toolCache` 保持，工具实例保持，research 节点直接用 `this.tools` |

### 文件结构

```
trip-server/src/services/agent/
├── agentEngine.ts          # 改：chat/recommend 内部走 graph，保留对外契约
├── plannerGraph.ts         # 新：LangGraph 状态图定义（research → planner → validate）
├── chatGraph.ts            # 新：chat 专用 graph（router → research → chat_planner | legacy_agent）
├── nodes/                  # 新：节点实现目录
│   ├── research.ts         # research 节点（确定性 fan-out）
│   ├── planner.ts          # planner 节点（recommend JSON 生成）
│   ├── chatPlanner.ts      # chat_planner 节点（markdown 流式）
│   ├── router.ts           # router 节点（规则式路由）
│   └── validate.ts         # validate + retry 节点
├── plannerPrompt.ts        # 新：planner / chatPlanner 系统 prompt（含 research bundle 注入）
├── state.ts                # 新：PlannerState Annotation 定义
├── tools/                  # 不动
├── systemPrompt.ts         # 不动（legacy agent 用）
├── resilience.ts          # 不动
├── toolCache.ts            # 不动
├── traceRecorder.ts        # 不动
└── types.ts                # 新：节点间共享类型（ResearchBundle、PlannerConfig）
```

### chat vs recommend graph 分离

两个 graph 而非一个：
- `plannerGraph`（recommend）：research → planner → validate → retry_planner
- `chatGraph`（chat）：router → (research → chat_planner) | legacy_agent

理由：recommend 走 `invoke()`（非流式，要整段 JSON），chat 走 `streamEvents()`（流式 markdown），事件模型不同，强行合一会引入条件分支复杂度。

## 错误处理

- research 节点：`Promise.allSettled`，单个工具失败用 fallback 文案，不阻塞 planner
- planner 节点：LLM 调用失败 → fallback LLM 重试 → 仍失败抛错（同现有）
- validate 节点：Zod 失败 → retry_planner 一次 → 仍失败抛错（同现有）
- chat_planner 节点：LLM 流式失败 → fallback LLM 重试（流式）→ 仍失败 emit error 事件
- legacy_agent 节点：完全不动，现有错误处理保留

## 测试策略

vitest + `vi.mock`，与现有 `__tests__/` 模式一致。每个节点独立单测：

- `nodes/research.test.ts`：mock 4 个工具，验证并行调用、查询词模板、allSettled 容错、事件 emit
- `nodes/router.test.ts`：纯函数，覆盖 planning/general 关键词矩阵
- `nodes/planner.test.ts`：mock LLM，验证 JSON 生成 + usage 累计
- `nodes/validate.test.ts`：mock extractJson + TripContentSchema，覆盖通过/失败/重试
- `plannerGraph.test.ts`：集成测试，mock 全部节点，验证 graph 执行顺序 + state 流转
- `chatGraph.test.ts`：集成测试，覆盖两条路由分支

legacy agent 不测（未改动）。

## 实施顺序

1. 装依赖 `@langchain/langgraph`
2. `state.ts` + `types.ts`（共享类型，无逻辑）
3. `nodes/router.ts` + 测试（最简单，纯函数）
4. `nodes/research.ts` + 测试（核心，独立可测）
5. `plannerPrompt.ts`（prompt 文案）
6. `nodes/planner.ts` + `nodes/validate.ts` + 测试
7. `plannerGraph.ts` + 集成测试
8. `nodes/chatPlanner.ts` + 测试
9. `chatGraph.ts` + 集成测试
10. `agentEngine.ts` 改造（接入两个 graph，保留对外契约）
11. 手动验证 recommend + chat 端到端
