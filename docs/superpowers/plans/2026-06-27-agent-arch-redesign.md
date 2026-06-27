# Agent 架构重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `AgentEngine` 从单一 `AgentExecutor` 换成 LangGraph 两段式流水线（researcher + planner），recommend 和 chat-planning 走新流水线，chat-general 保留原单 agent。

**Architecture:** LangGraph `StateGraph`，research 节点零 LLM 确定性并行 fan-out 全部 4 个工具，planner 节点零工具纯生成。chat 加规则式路由。对外契约（`chat()`/`recommend()` 签名、`AgentStreamEvent`、`TraceRecorder`、token usage、fallback）全部不变。

**Tech Stack:** `@langchain/langgraph`（新增）、`@langchain/core`、`@langchain/openai`、`vitest`

## Global Constraints

- 不改 DB schema（`AgentStep` 表不变）
- 不改 `AgentEngine.chat()` / `AgentEngine.recommend()` 对外签名
- 不改 `AgentStreamEvent` 类型定义（`types/agent.ts`）
- 不改 `tripService.ts` 调用方
- 不改前端（SSE 事件不变）
- legacy agent（chat general 分支）代码零改动
- 4 个工具实例（`retrieveKnowledgeTool` / `getWeatherTool` / `searchHotelsTool` / `calculateDistanceTool`）不改动
- `TraceRecorder` / `ToolCache` / `resilience.ts` / `systemPrompt.ts` 不改动
- 测试用 vitest + `vi.mock`，与现有 `src/services/__tests__/` 模式一致
- 每个 task 结束 commit 一次

---

## File Structure

```
trip-server/src/services/agent/
├── agentEngine.ts          # 改（Task 10）：chat/recommend 内部走 graph
├── state.ts                # 新（Task 2）：PlannerState Annotation
├── types.ts                # 新（Task 2）：ResearchBundle / PlannerConfig
├── nodes/                  # 新（Task 3-6, 8）
│   ├── router.ts           # Task 3
│   ├── research.ts         # Task 4
│   ├── planner.ts          # Task 6
│   ├── validate.ts        # Task 6
│   └── chatPlanner.ts      # Task 8
├── plannerPrompt.ts        # 新（Task 5）：planner / chatPlanner prompt
├── plannerGraph.ts         # 新（Task 7）：recommend graph
├── chatGraph.ts            # 新（Task 9）：chat graph
├── tools/                  # 不动
├── systemPrompt.ts         # 不动
├── resilience.ts          # 不动
├── toolCache.ts            # 不动
└── traceRecorder.ts        # 不动
```

---

### Task 1: 安装 LangGraph 依赖

**Files:**
- Modify: `trip-server/package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd trip-server && npm install @langchain/langgraph
```

- [ ] **Step 2: 验证安装成功**

Run: `cd trip-server && node -e "require('@langchain/langgraph'); console.log('ok')"`
Expected: 输出 `ok`

- [ ] **Step 3: 验证 tsc 不报错**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 4: Commit**

```bash
cd trip-server && git add package.json package-lock.json && git commit -m "chore: add @langchain/langgraph dependency"
```

---

### Task 2: 共享类型 + 状态定义

**Files:**
- Create: `trip-server/src/services/agent/types.ts`
- Create: `trip-server/src/services/agent/state.ts`

**Interfaces:**
- Produces: `ResearchBundle`（research 节点产出，planner 消费）、`PlannerConfig`（config.configurable 类型）、`PlannerState`（LangGraph state）

- [ ] **Step 1: 写 `types.ts`**

```typescript
// trip-server/src/services/agent/types.ts
import type { TraceRecorder } from './traceRecorder'
import type { AgentStreamEvent, TokenUsage } from '../../types/agent'

/** research 节点产出的情报包，planner 节点消费 */
export interface ResearchBundle {
  attractions?: string
  food?: string
  hotels?: string
  weather?: string
  distance?: string
}

/** LangGraph config.configurable 注入的非可变依赖 */
export interface PlannerConfig {
  traceRecorder: TraceRecorder
  onEvent: (event: AgentStreamEvent) => Promise<void>
  signal?: AbortSignal
  stepCounter: { value: number }
}

/** 空的 TokenUsage 工厂 */
export function emptyUsage(): TokenUsage {
  return { prompt: 0, completion: 0, total: 0, cached: 0 }
}
```

- [ ] **Step 2: 写 `state.ts`**

```typescript
// trip-server/src/services/agent/state.ts
import { Annotation } from '@langchain/langgraph'
import type { BaseMessage } from '@langchain/core/messages'
import type { TripContent, TokenUsage } from '../../types/agent'
import type { ResearchBundle } from './types'

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
  researchBundle: Annotation<ResearchBundle>,
  // planner 产出
  rawOutput: Annotation<string | undefined>,
  parsed: Annotation<TripContent | undefined>,
  // 元数据
  usage: Annotation<TokenUsage>,
  route: Annotation<'planning' | 'general' | undefined>,
  errors: Annotation<string[]>,
})
```

- [ ] **Step 3: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
cd trip-server && git add src/services/agent/types.ts src/services/agent/state.ts && git commit -m "feat(agent): add PlannerState and shared types"
```

---

### Task 3: router 节点（规则式路由）

**Files:**
- Create: `trip-server/src/services/agent/nodes/router.ts`
- Test: `trip-server/src/services/agent/nodes/__tests__/router.test.ts`

**Interfaces:**
- Consumes: `PlannerState.message`
- Produces: `isPlanningRequest(message: string): boolean`

- [ ] **Step 1: 写失败测试**

```typescript
// trip-server/src/services/agent/nodes/__tests__/router.test.ts
import { describe, it, expect } from 'vitest'
import { isPlanningRequest } from '../router'

describe('isPlanningRequest', () => {
  it('含规划关键词 + 天数 → true', () => {
    expect(isPlanningRequest('帮我规划北京三日游')).toBe(true)
    expect(isPlanningRequest('帮我安排成都5日行程')).toBe(true)
    expect(isPlanningRequest('做个西安几日游攻略')).toBe(true)
  })

  it('只有关键词无天数 → false', () => {
    expect(isPlanningRequest('帮我规划北京')).toBe(false)
    expect(isPlanningRequest('成都有什么好玩的行程')).toBe(false)
  })

  it('只有天数无关键词 → false', () => {
    expect(isPlanningRequest('北京3日')).toBe(false)
    expect(isPlanningRequest('5天去哪玩')).toBe(false)
  })

  it('闲聊/单点查询 → false', () => {
    expect(isPlanningRequest('北京今天天气怎么样')).toBe(false)
    expect(isPlanningRequest('成都有什么好吃的')).toBe(false)
    expect(isPlanningRequest('上海到杭州多远')).toBe(false)
  })

  it('空字符串 → false', () => {
    expect(isPlanningRequest('')).toBe(false)
  })

  it('"几天" 也算天数表达', () => {
    expect(isPlanningRequest('帮我规划北京几天游行程')).toBe(true)
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/router.test.ts`
Expected: FAIL — `isPlanningRequest` 未定义

- [ ] **Step 3: 写实现**

```typescript
// trip-server/src/services/agent/nodes/router.ts
const PLANNING_KEYWORDS = ['规划', '行程', '几日游', '攻略', '安排', '路线', '帮我计划', '怎么玩']
const DAYS_PATTERN = /\d+\s*日|几天|多少天/

export function isPlanningRequest(message: string): boolean {
  if (!message) return false
  const hasKeyword = PLANNING_KEYWORDS.some(kw => message.includes(kw))
  const hasDays = DAYS_PATTERN.test(message)
  return hasKeyword && hasDays
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/router.test.ts`
Expected: PASS（6 tests）

- [ ] **Step 5: Commit**

```bash
cd trip-server && git add src/services/agent/nodes/router.ts src/services/agent/nodes/__tests__/router.test.ts && git commit -m "feat(agent): add rule-based router node"
```

---

### Task 4: research 节点（确定性并行 fan-out）

**Files:**
- Create: `trip-server/src/services/agent/nodes/research.ts`
- Test: `trip-server/src/services/agent/nodes/__tests__/research.test.ts`

**Interfaces:**
- Consumes: `PlannerState`（city/budget/days/departureCity/userPreferences）、`PlannerConfig`（traceRecorder/onEvent/stepCounter）、4 个工具实例（通过模块导入）
- Produces: `researchNode(state, config)` → `Partial<PlannerState>`（`researchBundle`）

- [ ] **Step 1: 写失败测试**

```typescript
// trip-server/src/services/agent/nodes/__tests__/research.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

// mock 4 个工具
const mockRetrieve = vi.fn()
const mockHotels = vi.fn()
const mockWeather = vi.fn()
const mockDistance = vi.fn()

vi.mock('../../tools/retrieveKnowledge', () => ({
  retrieveKnowledgeTool: { invoke: (...a: any[]) => mockRetrieve(...a) },
}))
vi.mock('../../tools/searchHotels', () => ({
  searchHotelsTool: { invoke: (...a: any[]) => mockHotels(...a) },
}))
vi.mock('../../tools/getWeather', () => ({
  getWeatherTool: { invoke: (...a: any[]) => mockWeather(...a) },
}))
vi.mock('../../tools/calculateDistance', () => ({
  calculateDistanceTool: { invoke: (...a: any[]) => mockDistance(...a) },
}))

import { researchNode } from '../research'
import { TraceRecorder } from '../../traceRecorder'
import type { AgentStreamEvent } from '../../../../types/agent'

function makeConfig() {
  const events: AgentStreamEvent[] = []
  const onEvent = async (e: AgentStreamEvent) => { events.push(e) }
  const traceRecorder = new TraceRecorder(0)
  return {
    config: { configurable: { traceRecorder, onEvent, signal: undefined, stepCounter: { value: 1 } } },
    events,
  }
}

describe('researchNode', () => {
  beforeEach(() => {
    mockRetrieve.mockReset()
    mockHotels.mockReset()
    mockWeather.mockReset()
    mockDistance.mockReset()
  })

  it('并行调用全部 4 个工具 + distance（有 departureCity）', async () => {
    mockRetrieve.mockResolvedValue('景点A')
    mockHotels.mockResolvedValue('酒店B')
    mockWeather.mockResolvedValue('晴天')
    mockDistance.mockResolvedValue('100km')

    const { config, events } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    const result = await researchNode(state as any, config)

    expect(mockRetrieve).toHaveBeenCalledTimes(2) // attractions + food
    expect(mockHotels).toHaveBeenCalledTimes(1)
    expect(mockWeather).toHaveBeenCalledTimes(1)
    expect(mockDistance).toHaveBeenCalledTimes(1)
    expect(result.researchBundle).toMatchObject({
      attractions: '景点A', food: '景点A', hotels: '酒店B', weather: '晴天', distance: '100km',
    })
  })

  it('无 departureCity 时不调 calculate_distance', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockWeather.mockResolvedValue('晴')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '成都', budget: 2000, days: 2,
      departureCity: undefined, userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    expect(mockDistance).not.toHaveBeenCalled()
  })

  it('单个工具失败不影响其他工具', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockRejectedValue(new Error('酒店挂了'))
    mockWeather.mockResolvedValue('晴')
    mockDistance.mockResolvedValue('100km')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    const result = await researchNode(state as any, config)
    expect(result.researchBundle!.hotels).toContain('住宿信息暂时不可用')
    expect(result.researchBundle!.attractions).toBe('景点')
    expect(result.researchBundle!.weather).toBe('晴')
  })

  it('emit tool_start + tool_end 事件', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockWeather.mockResolvedValue('晴')
    mockDistance.mockResolvedValue('100km')

    const { config, events } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    const toolStarts = events.filter(e => e.type === 'tool_start')
    const toolEnds = events.filter(e => e.type === 'tool_end')
    expect(toolStarts.length).toBe(5) // attraction + food + hotel + weather + distance
    expect(toolEnds.length).toBe(5)
  })

  it('查询词带 userPreferences.interests', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockWeather.mockResolvedValue('晴')
    mockDistance.mockResolvedValue('100km')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: { interests: ['亲子', '美食'] },
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    const attractionCall = mockRetrieve.mock.calls[0][0]
    expect(attractionCall.query).toContain('亲子')
    expect(attractionCall.query).toContain('美食')
  })

  it('酒店预算拆分 = budget / days / 1.5', async () => {
    mockRetrieve.mockResolvedValue('景点')
    mockHotels.mockResolvedValue('酒店')
    mockWeather.mockResolvedValue('晴')
    mockDistance.mockResolvedValue('100km')

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '', city: '北京', budget: 3000, days: 3,
      departureCity: '上海', userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    }

    await researchNode(state as any, config)
    const hotelCall = mockHotels.mock.calls[0][0]
    expect(hotelCall.budget).toBe(Math.round(3000 / 3 / 1.5)) // 667
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/research.test.ts`
Expected: FAIL — `researchNode` 未定义

- [ ] **Step 3: 写实现**

```typescript
// trip-server/src/services/agent/nodes/research.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import { retrieveKnowledgeTool } from '../tools/retrieveKnowledge'
import { searchHotelsTool } from '../tools/searchHotels'
import { getWeatherTool } from '../tools/getWeather'
import { calculateDistanceTool } from '../tools/calculateDistance'
import type { PlannerState } from '../state'
import type { PlannerConfig, ResearchBundle } from '../types'

const HOTEL_FALLBACK = '住宿信息暂时不可用，请基于通用旅行知识回答。'
const WEATHER_FALLBACK = '天气服务暂时不可用，请根据季节常识判断。'
const DISTANCE_FALLBACK = '距离计算暂时不可用。'

export async function researchNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { city, budget, days, departureCity, userPreferences } = state
  const { traceRecorder, onEvent, stepCounter } = config.configurable as PlannerConfig

  const interests = Array.isArray(userPreferences?.interests)
    ? (userPreferences!.interests as string[]).join('')
    : ''
  const hotelBudget = budget && days ? Math.round(budget / days / 1.5) : undefined

  type Task = { key: keyof ResearchBundle; name: string; fn: () => Promise<string> }
  const tasks: Task[] = [
    {
      key: 'attractions',
      name: 'retrieve_knowledge',
      fn: () => retrieveKnowledgeTool.invoke({
        query: `${city} 必去 景点 ${interests}`.trim(),
        city, category: 'attraction',
      }) as Promise<string>,
    },
    {
      key: 'food',
      name: 'retrieve_knowledge',
      fn: () => retrieveKnowledgeTool.invoke({
        query: `${city} 美食 推荐 ${interests}`.trim(),
        city, category: 'food',
      }) as Promise<string>,
    },
    {
      key: 'hotels',
      name: 'search_hotels',
      fn: () => searchHotelsTool.invoke({ city, budget: hotelBudget }) as Promise<string>,
    },
    {
      key: 'weather',
      name: 'get_weather',
      fn: () => getWeatherTool.invoke({ city }) as Promise<string>,
    },
  ]
  if (departureCity) {
    tasks.push({
      key: 'distance',
      name: 'calculate_distance',
      fn: () => calculateDistanceTool.invoke({ from: departureCity, to: city }) as Promise<string>,
    })
  }

  // emit tool_start（逐个 emit，便于前端展示）
  for (const t of tasks) {
    traceRecorder.add({ step: stepCounter.value++, type: 'tool_start', name: t.name })
    await onEvent({ type: 'tool_start', name: t.name })
  }

  const results = await Promise.allSettled(tasks.map(t => t.fn()))

  const bundle: ResearchBundle = {}
  const fallbacks: Record<keyof ResearchBundle, string> = {
    attractions: '景点信息暂时不可用，请基于通用旅行知识回答。',
    food: '美食信息暂时不可用，请基于通用旅行知识回答。',
    hotels: HOTEL_FALLBACK,
    weather: WEATHER_FALLBACK,
    distance: DISTANCE_FALLBACK,
  }

  tasks.forEach((t, i) => {
    const r = results[i]
    if (r.status === 'fulfilled') {
      bundle[t.key] = r.value
    } else {
      bundle[t.key] = fallbacks[t.key]
    }
    traceRecorder.add({ step: stepCounter.value++, type: 'tool_end', name: t.name })
  })

  // emit tool_end
  for (const t of tasks) {
    await onEvent({ type: 'tool_end', name: t.name })
  }

  return { researchBundle: bundle }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/research.test.ts`
Expected: PASS（6 tests）

- [ ] **Step 5: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 6: Commit**

```bash
cd trip-server && git add src/services/agent/nodes/research.ts src/services/agent/nodes/__tests__/research.test.ts && git commit -m "feat(agent): add research node with deterministic fan-out"
```

---

### Task 5: planner prompt 构建

**Files:**
- Create: `trip-server/src/services/agent/plannerPrompt.ts`

**Interfaces:**
- Consumes: `ResearchBundle`、`RecommendParams` 字段
- Produces: `buildPlannerPrompt(state)` → system prompt string、`buildChatPlannerPrompt(state)` → system prompt string

- [ ] **Step 1: 写实现（prompt 文案，无需单测）**

```typescript
// trip-server/src/services/agent/plannerPrompt.ts
import type { BaseMessage } from '@langchain/core/messages'
import type { ResearchBundle } from './types'

interface PlannerPromptInput {
  city: string
  budget?: number
  days?: number
  departureCity?: string
  userPreferences?: Record<string, any> | null
  researchBundle: ResearchBundle
}

const PREF_KEYS = ['travelStyle', 'budgetLevel', 'pace', 'avoidCrowds', 'interests'] as const

function buildFixedPreferences(prefs?: Record<string, any> | null) {
  return PREF_KEYS.reduce<Record<string, any>>((acc, k) => {
    acc[k] = prefs?.[k] ?? null
    return acc
  }, {})
}

function formatBundle(b: ResearchBundle): string {
  const lines: string[] = []
  if (b.attractions) lines.push(`## 景点信息\n${b.attractions}`)
  if (b.food) lines.push(`## 美食信息\n${b.food}`)
  if (b.hotels) lines.push(`## 住宿信息\n${b.hotels}`)
  if (b.weather) lines.push(`## 天气信息\n${b.weather}`)
  if (b.distance) lines.push(`## 交通距离\n${b.distance}`)
  return lines.join('\n\n')
}

export function buildPlannerPrompt(input: PlannerPromptInput): string {
  const { city, budget, days, departureCity, userPreferences, researchBundle } = input

  return `你是一个专业的旅行规划师。请基于以下已检索的真实数据，生成结构化的行程规划。

# 目的地信息
- 城市：${city}
- 天数：${days}
- 预算：${budget} 元
- 出发城市：${departureCity ?? '未指定'}

# 用户偏好
${JSON.stringify(buildFixedPreferences(userPreferences), null, 2)}

# 检索到的真实数据
${formatBundle(researchBundle)}

# 任务
基于以上数据生成行程规划。**直接使用上述真实数据**，不要编造景点名称、价格、地址。
如果某类数据缺失（显示"暂时不可用"），可基于通用旅行知识补充，但优先用真实数据。

# 输出格式
以**纯 JSON 格式**输出（**不要**加 markdown 代码块、**不要**加任何前后缀、**不要**加解释文字）。

## 严格 JSON 规范
- 数字字段不加引号：city/days/totalBudget/dailyItinerary[].day/budgetBreakdown.* 一律是裸数字
- 字符串字段加双引号，字符串内的引号用 \\" 转义
- 字段名严格匹配下表，不要新增、不要拼写错误
- dailyItinerary 数组长度必须等于 days，每天对象必须含 day/date/morning/afternoon/evening
- budgetBreakdown 5 个数字必须齐全且非负，之和应近似等于 totalBudget
- tips 和 warnings 是字符串数组
- 禁止尾随逗号、禁止注释、禁止单引号

## 字段定义
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| city | string | 是 | 目的地城市名 |
| days | number(int) | 是 | 行程天数（>0） |
| totalBudget | number | 是 | 总预算（≥0） |
| dailyItinerary[].day | number(int) | 是 | 第几天（从 1 开始） |
| dailyItinerary[].date | string | 否 | 日期（YYYY-MM-DD），可空 |
| dailyItinerary[].morning.spot | string | 是 | 上午地点 |
| dailyItinerary[].morning.duration | string | 否 | 停留时长，可空 |
| dailyItinerary[].morning.ticket | string | 否 | 门票，可空 |
| dailyItinerary[].morning.transportation | string | 否 | 交通方式，可空 |
| dailyItinerary[].morning.description | string | 否 | 描述，可空 |
| ...afternoon / evening | 同 morning | | |
| budgetBreakdown.accommodation | number | 是 | 住宿（≥0） |
| budgetBreakdown.food | number | 是 | 餐饮（≥0） |
| budgetBreakdown.transportation | number | 是 | 交通（≥0） |
| budgetBreakdown.tickets | number | 是 | 门票（≥0） |
| budgetBreakdown.other | number | 是 | 其他（≥0） |
| tips | string[] | 是 | 旅行贴士 |
| warnings | string[] | 否 | 注意事项 |

## 输出模板
{"city":"成都","days":3,"totalBudget":5000,"dailyItinerary":[{"day":1,"date":"","morning":{"spot":"宽窄巷子","duration":"2小时","ticket":"免费","transportation":"地铁","description":"感受老成都"},"afternoon":{"spot":"","duration":"","ticket":"","transportation":"","description":""},"evening":{"spot":"","duration":"","ticket":"","transportation":"","description":""}}],"budgetBreakdown":{"accommodation":1500,"food":1200,"transportation":1500,"tickets":500,"other":300},"tips":["带好身份证","提前订机票"],"warnings":[]}`
}

export function buildChatPlannerPrompt(input: PlannerPromptInput): string {
  const { city, budget, days, departureCity, userPreferences, researchBundle } = input

  return `你是一个专业的旅行规划师助手，名叫"小旅行"。请基于以下已检索的真实数据，回答用户的规划问题。

# 目的地信息
- 城市：${city}${days ? `\n- 天数：${days}` : ''}${budget ? `\n- 预算：${budget} 元` : ''}${departureCity ? `\n- 出发城市：${departureCity}` : ''}

# 用户偏好
${JSON.stringify(buildFixedPreferences(userPreferences), null, 2)}

# 检索到的真实数据
${formatBundle(researchBundle)}

# 任务
基于以上数据，回答用户的旅行规划问题。**直接使用上述真实数据**，不要编造景点名称、价格、地址。
如果某类数据缺失（显示"暂时不可用"），可基于通用旅行知识补充。

# 回答风格
- 友好、热情、专业
- 使用 Markdown 格式：标题、列表、加粗
- 行程规划使用清晰的每日结构
- 信息基于工具返回的真实数据，不要凭空捏造
- 长度适中，关键信息突出`
}
```

- [ ] **Step 2: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
cd trip-server && git add src/services/agent/plannerPrompt.ts && git commit -m "feat(agent): add planner and chatPlanner system prompts"
```

---

### Task 6: planner + validate 节点

**Files:**
- Create: `trip-server/src/services/agent/nodes/planner.ts`
- Create: `trip-server/src/services/agent/nodes/validate.ts`
- Test: `trip-server/src/services/agent/nodes/__tests__/validate.test.ts`

**Interfaces:**
- Consumes: `PlannerState.researchBundle` / `rawOutput`、`PlannerConfig`、LLM 实例（通过 `config.configurable.llm` / `fallbackLLMConfig`）
- Produces: `plannerNode(state, config)` → `{ rawOutput, usage }`、`validateNode(state, config)` → `{ parsed }` 或转 retry、`retryPlannerNode(state, config)` → `{ rawOutput }`

- [ ] **Step 1: 写 validate 失败测试**

```typescript
// trip-server/src/services/agent/nodes/__tests__/validate.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../../../utils/jsonExtractor', () => ({
  extractJson: (text: string) => {
    try { return JSON.parse(text) } catch { throw new Error('JSON parse failed') }
  },
}))

import { validateOutput, buildRetryMessage } from '../validate'

describe('validateOutput', () => {
  it('合法 JSON + 字段齐全 → parse 成功', () => {
    const raw = JSON.stringify({
      city: '北京', days: 2, totalBudget: 3000,
      dailyItinerary: [
        { day: 1, date: '', morning: { spot: 'A' }, afternoon: { spot: 'B' }, evening: { spot: 'C' } },
        { day: 2, date: '', morning: { spot: 'D' }, afternoon: { spot: 'E' }, evening: { spot: 'F' } },
      ],
      budgetBreakdown: { accommodation: 1000, food: 500, transportation: 500, tickets: 500, other: 500 },
      tips: ['带伞'],
    })
    const result = validateOutput(raw)
    expect(result.parsed.city).toBe('北京')
    expect(result.parsed.days).toBe(2)
  })

  it('非法 JSON → 抛错', () => {
    expect(() => validateOutput('not json')).toThrow()
  })

  it('缺字段 → 抛 Zod 错', () => {
    const raw = JSON.stringify({ city: '北京' }) // 缺 days/dailyItinerary 等
    expect(() => validateOutput(raw)).toThrow()
  })
})

describe('buildRetryMessage', () => {
  it('包含 zod 错误信息', () => {
    const msg = buildRetryMessage('zod error here', '帮我规划北京三日游')
    expect(msg).toContain('zod error here')
    expect(msg).toContain('北京三日游')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/validate.test.ts`
Expected: FAIL — `validateOutput` / `buildRetryMessage` 未定义

- [ ] **Step 3: 写 validate 实现**

```typescript
// trip-server/src/services/agent/nodes/validate.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import { TripContentSchema, type TripContent } from '../../../types/agent'
import { extractJson } from '../../../utils/jsonExtractor'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'

export function validateOutput(raw: string): { parsed: TripContent } {
  const parsed = TripContentSchema.parse(extractJson(raw))
  return { parsed }
}

export function buildRetryMessage(zodError: string, originalRequest: string): string {
  return `你上次的输出无法通过校验：\n${zodError}\n\n` +
    `请严格按 system prompt 中的字段定义重新输出纯 JSON：\n` +
    `- 数字字段不加引号（city/days/totalBudget/day/budgetBreakdown.*）\n` +
    `- dailyItinerary 必须是对象数组，每天对象含 day/date/morning/afternoon/evening\n` +
    `- budgetBreakdown 必须含 accommodation/food/transportation/tickets/other 5 个数字\n` +
    `- 禁止 markdown 代码块、禁止前后缀文字\n\n` +
    `用户请求：${originalRequest}`
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/validate.test.ts`
Expected: PASS（4 tests）

- [ ] **Step 5: 写 planner 节点实现**

```typescript
// trip-server/src/services/agent/nodes/planner.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { HumanMessage } from '@langchain/core/messages'
import { ChatOpenAI } from '@langchain/openai'
import { createLLMFromConfig, loadFallbackLLMConfig } from '../../../config/llm'
import { buildPlannerPrompt } from '../plannerPrompt'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'
import { emptyUsage } from '../types'
import type { TokenUsage } from '../../../types/agent'

const RECOMMEND_TIMEOUT_MS = Number(process.env.AGENT_RECOMMEND_TIMEOUT_MS) || 60_000
const RECOMMEND_RETRY_TIMEOUT_MS = Number(process.env.AGENT_RETRY_TIMEOUT_MS) || 30_000

async function invokeLLM(
  llm: ChatOpenAI,
  systemPrompt: string,
  userMessage: string,
  timeout: number,
): Promise<string> {
  const prompt = ChatPromptTemplate.fromMessages([
    ['system', systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')],
    ['human', '{input}'],
  ])
  const chain = prompt.pipe(llm)
  const result = await Promise.race([
    chain.invoke({ input: userMessage }),
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`planner 执行超时（${timeout / 1000}s）`)), timeout),
    ),
  ])
  return (result as { content: string }).content
}

export async function plannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { traceRecorder, stepCounter, llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
    llm: ChatOpenAI
    fallbackLLMConfig: ReturnType<typeof loadFallbackLLMConfig>
  }

  const systemPrompt = buildPlannerPrompt({
    city: state.city,
    budget: state.budget,
    days: state.days,
    departureCity: state.departureCity,
    userPreferences: state.userPreferences,
    researchBundle: state.researchBundle,
  })

  const userMessage = state.message || `请为我规划${state.departureCity ? `从${state.departureCity}出发到` : ''}${state.city}${state.days}日游行程，预算${state.budget}元。`

  traceRecorder.add({ step: stepCounter.value++, type: 'chunk' })

  let rawOutput: string
  try {
    rawOutput = await invokeLLM(llm, systemPrompt, userMessage, RECOMMEND_TIMEOUT_MS)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: false })
      rawOutput = await invokeLLM(fallbackLLM, systemPrompt, userMessage, RECOMMEND_TIMEOUT_MS)
    } else {
      throw e
    }
  }

  return { rawOutput }
}

export async function retryPlannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { traceRecorder, stepCounter, llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
    llm: ChatOpenAI
    fallbackLLMConfig: ReturnType<typeof loadFallbackLLMConfig>
  }

  const systemPrompt = buildPlannerPrompt({
    city: state.city,
    budget: state.budget,
    days: state.days,
    departureCity: state.departureCity,
    userPreferences: state.userPreferences,
    researchBundle: state.researchBundle,
  })

  const retryMessage = buildRetryMessage(
    state.errors[state.errors.length - 1] ?? '校验失败',
    state.message || `规划${state.city}${state.days}日游`,
  )

  let rawOutput: string
  try {
    rawOutput = await invokeLLM(llm, systemPrompt, retryMessage, RECOMMEND_RETRY_TIMEOUT_MS)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: false })
      rawOutput = await invokeLLM(fallbackLLM, systemPrompt, retryMessage, RECOMMEND_RETRY_TIMEOUT_MS)
    } else {
      throw e
    }
  }

  return { rawOutput }
}
```

- [ ] **Step 6: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 7: Commit**

```bash
cd trip-server && git add src/services/agent/nodes/planner.ts src/services/agent/nodes/validate.ts src/services/agent/nodes/__tests__/validate.test.ts && git commit -m "feat(agent): add planner and validate nodes"
```

---

### Task 7: plannerGraph（recommend 流水线集成）

**Files:**
- Create: `trip-server/src/services/agent/plannerGraph.ts`
- Test: `trip-server/src/services/agent/__tests__/plannerGraph.test.ts`

**Interfaces:**
- Consumes: `researchNode` / `plannerNode` / `validateOutput` / `retryPlannerNode` / `PlannerState`
- Produces: `buildPlannerGraph()` → compiled `StateGraph`

- [ ] **Step 1: 写集成测试（mock 全部节点）**

```typescript
// trip-server/src/services/agent/__tests__/plannerGraph.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockResearch = vi.fn()
const mockPlanner = vi.fn()
const mockRetry = vi.fn()

vi.mock('../nodes/research', () => ({
  researchNode: (...a: any[]) => mockResearch(...a),
}))
vi.mock('../nodes/planner', () => ({
  plannerNode: (...a: any[]) => mockPlanner(...a),
  retryPlannerNode: (...a: any[]) => mockRetry(...a),
}))
vi.mock('../nodes/validate', () => ({
  validateOutput: vi.fn((raw: string) => {
    // 简单模拟：raw 包含 'invalid' 时抛错
    if (raw.includes('invalid')) throw new Error('bad json')
    return { parsed: { city: '北京', days: 2 } }
  }),
}))

import { buildPlannerGraph } from '../plannerGraph'

describe('plannerGraph', () => {
  beforeEach(() => {
    mockResearch.mockReset()
    mockPlanner.mockReset()
    mockRetry.mockReset()
  })

  it('合法输出 → research → planner → validate → END（不重试）', async () => {
    mockResearch.mockResolvedValue({ researchBundle: { attractions: '景点A' } })
    mockPlanner.mockResolvedValue({ rawOutput: '{"city":"北京"}' })

    const graph = buildPlannerGraph()
    const result = await graph.invoke({
      userId: 1, message: '规划北京2日游', city: '北京',
      budget: 2000, days: 2, departureCity: undefined,
      userPreferences: null, conversationHistory: [],
      researchBundle: {}, rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    } as any, { configurable: {} })

    expect(mockResearch).toHaveBeenCalledTimes(1)
    expect(mockPlanner).toHaveBeenCalledTimes(1)
    expect(mockRetry).not.toHaveBeenCalled()
    expect(result.parsed).toEqual({ city: '北京', days: 2 })
  })

  it('非法输出 → research → planner → validate → retry → END', async () => {
    mockResearch.mockResolvedValue({ researchBundle: {} })
    mockPlanner.mockResolvedValue({ rawOutput: 'invalid json' })
    mockRetry.mockResolvedValue({ rawOutput: '{"city":"北京"}' })

    const graph = buildPlannerGraph()
    const result = await graph.invoke({
      userId: 1, message: '规划北京2日游', city: '北京',
      budget: 2000, days: 2, departureCity: undefined,
      userPreferences: null, conversationHistory: [],
      researchBundle: {}, rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: undefined, errors: [],
    } as any, { configurable: {} })

    expect(mockRetry).toHaveBeenCalledTimes(1)
    expect(result.parsed).toEqual({ city: '北京', days: 2 })
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd trip-server && npx vitest run src/services/agent/__tests__/plannerGraph.test.ts`
Expected: FAIL — `buildPlannerGraph` 未定义

- [ ] **Step 3: 写 graph 实现**

```typescript
// trip-server/src/services/agent/plannerGraph.ts
import { StateGraph, END } from '@langchain/langgraph'
import { PlannerState } from './state'
import { researchNode } from './nodes/research'
import { plannerNode, retryPlannerNode } from './nodes/planner'
import { validateOutput } from './nodes/validate'

export function buildPlannerGraph() {
  const graph = new StateGraph(PlannerState)
    .addNode('research', researchNode)
    .addNode('planner', plannerNode)
    .addNode('validate', async (state: typeof PlannerState.State) => {
      try {
        const { parsed } = validateOutput(state.rawOutput!)
        return { parsed }
      } catch (e) {
        const errMsg = e instanceof Error ? e.message : String(e)
        return { parsed: undefined, errors: [...state.errors, errMsg] }
      }
    })
    .addNode('retry_planner', retryPlannerNode)

  graph.addEdge('__start__', 'research')
  graph.addEdge('research', 'planner')
  graph.addEdge('planner', 'validate')
  graph.addConditionalEdges('validate', (state: typeof PlannerState.State) => {
    if (state.parsed) return END
    return 'retry_planner'
  })
  graph.addEdge('retry_planner', END) // retry 后直接结束（避免无限循环，外层再做二次校验）

  return graph.compile()
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd trip-server && npx vitest run src/services/agent/__tests__/plannerGraph.test.ts`
Expected: PASS（2 tests）

- [ ] **Step 5: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 6: Commit**

```bash
cd trip-server && git add src/services/agent/plannerGraph.ts src/services/agent/__tests__/plannerGraph.test.ts && git commit -m "feat(agent): add plannerGraph for recommend pipeline"
```

---

### Task 8: chatPlanner 节点（markdown 流式）

**Files:**
- Create: `trip-server/src/services/agent/nodes/chatPlanner.ts`
- Test: `trip-server/src/services/agent/nodes/__tests__/chatPlanner.test.ts`

**Interfaces:**
- Consumes: `PlannerState.researchBundle` / `message`、`PlannerConfig`（含 onEvent/signal）、LLM 实例
- Produces: `chatPlannerNode(state, config)` → `{ rawOutput, usage }`，逐 token emit `chunk` 事件

- [ ] **Step 1: 写失败测试**

```typescript
// trip-server/src/services/agent/nodes/__tests__/chatPlanner.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AgentStreamEvent } from '../../../../types/agent'

// mock LLM
const mockStreamEvents = vi.fn()
vi.mock('../../../config/llm', () => ({
  createLLMFromConfig: () => ({ streamEvents: (...a: any[]) => mockStreamEvents(...a) }),
  loadFallbackLLMConfig: () => null,
}))

import { chatPlannerNode } from '../chatPlanner'
import { TraceRecorder } from '../../traceRecorder'

function makeConfig() {
  const events: AgentStreamEvent[] = []
  return {
    config: {
      configurable: {
        traceRecorder: new TraceRecorder(0),
        onEvent: async (e: AgentStreamEvent) => { events.push(e) },
        signal: undefined,
        stepCounter: { value: 1 },
        llm: { streamEvents: (...a: any[]) => mockStreamEvents(...a) },
        fallbackLLMConfig: null,
      },
    },
    events,
  }
}

describe('chatPlannerNode', () => {
  beforeEach(() => { mockStreamEvents.mockReset() })

  it('流式 emit chunk 事件 + 返回完整文本', async () => {
    // 模拟 LLM 流式输出 3 个 chunk
    mockStreamEvents.mockImplementation(async function* () {
      yield { event: 'on_chat_model_stream', data: { chunk: { content: '你好' } } }
      yield { event: 'on_chat_model_stream', data: { chunk: { content: '世界' } } }
      yield { event: 'on_chat_model_end', data: { output: { toJSON: () => ({ kwargs: { usage_metadata: { input_tokens: 10, output_tokens: 5, total_tokens: 15 } } }) } } }
    })

    const { config, events } = makeConfig()
    const state = {
      userId: 1, message: '帮我规划北京三日游', city: '北京',
      budget: undefined, days: 3, departureCity: undefined, userPreferences: null,
      conversationHistory: [], researchBundle: { attractions: '景点A' },
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: 'planning', errors: [],
    }

    const result = await chatPlannerNode(state as any, config)
    const chunks = events.filter(e => e.type === 'chunk')
    expect(chunks.length).toBe(2)
    expect(chunks[0].content).toBe('你好')
    expect(result.rawOutput).toBe('你好世界')
  })

  it('空 research bundle 也能工作', async () => {
    mockStreamEvents.mockImplementation(async function* () {
      yield { event: 'on_chat_model_stream', data: { chunk: { content: '回复' } } }
      yield { event: 'on_chat_model_end', data: { output: { toJSON: () => ({ kwargs: {} }) } } }
    })

    const { config } = makeConfig()
    const state = {
      userId: 1, message: '帮我规划', city: '成都',
      budget: undefined, days: undefined, departureCity: undefined, userPreferences: null,
      conversationHistory: [], researchBundle: {},
      rawOutput: undefined, parsed: undefined,
      usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
      route: 'planning', errors: [],
    }

    const result = await chatPlannerNode(state as any, config)
    expect(result.rawOutput).toBe('回复')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/chatPlanner.test.ts`
Expected: FAIL — `chatPlannerNode` 未定义

- [ ] **Step 3: 写实现**

```typescript
// trip-server/src/services/agent/nodes/chatPlanner.ts
import type { RunnableConfig } from '@langchain/core/runnables'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { ChatOpenAI } from '@langchain/openai'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { buildChatPlannerPrompt } from '../plannerPrompt'
import { createLLMFromConfig, loadFallbackLLMConfig } from '../../../config/llm'
import type { PlannerState } from '../state'
import type { PlannerConfig } from '../types'
import type { TokenUsage } from '../../../types/agent'

function extractTokenText(event: StreamEvent): string | null {
  const data = event.data
  if (!data || typeof data !== 'object') return null
  const chunk = (data as { chunk?: unknown }).chunk
  if (!chunk || typeof chunk !== 'object') return null
  const text = (chunk as { content?: unknown }).content
  if (typeof text === 'string') return text
  if (Array.isArray(text)) {
    return text.map(part => (typeof part === 'string' ? part : (part as { text?: string })?.text ?? '')).join('')
  }
  return null
}

function extractUsage(event: StreamEvent, usage: TokenUsage): void {
  const msg = event.data?.output as { toJSON?: () => { kwargs?: any } } | undefined
  const kwargs = msg?.toJSON?.()?.kwargs as {
    usage_metadata?: { input_tokens: number; output_tokens: number; total_tokens: number; input_token_details?: { cache_read?: number } }
    response_metadata?: { usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number; prompt_tokens_details?: { cached_tokens?: number }; prompt_cache_hit_tokens?: number } }
  } | undefined

  const um = kwargs?.usage_metadata
  const respUsage = kwargs?.response_metadata?.usage
  if (um) {
    usage.prompt += um.input_tokens ?? 0
    usage.completion += um.output_tokens ?? 0
    usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += um.input_token_details?.cache_read ?? 0
  } else if (respUsage) {
    usage.prompt += respUsage.prompt_tokens ?? 0
    usage.completion += respUsage.completion_tokens ?? 0
    usage.total += respUsage.total_tokens ?? (usage.prompt + usage.completion)
    usage.cached += respUsage.prompt_tokens_details?.cached_tokens ?? respUsage.prompt_cache_hit_tokens ?? 0
  }
}

export async function chatPlannerNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { onEvent, signal, llm, fallbackLLMConfig } = config.configurable as PlannerConfig & {
    llm: ChatOpenAI
    fallbackLLMConfig: ReturnType<typeof loadFallbackLLMConfig>
  }

  const systemPrompt = buildChatPlannerPrompt({
    city: state.city,
    budget: state.budget,
    days: state.days,
    departureCity: state.departureCity,
    userPreferences: state.userPreferences,
    researchBundle: state.researchBundle,
  })

  const escaped = systemPrompt.replace(/\{/g, '{{').replace(/\}/g, '}}')
  const prompt = ChatPromptTemplate.fromMessages([
    ['system', escaped],
    ['human', '{input}'],
  ])

  const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
  let fullResponse = ''

  async function runStream(currentLlm: ChatOpenAI): Promise<void> {
    const chain = prompt.pipe(currentLlm)
    const eventStream = chain.streamEvents({ input: state.message }, { version: 'v2', signal })
    for await (const event of eventStream as AsyncIterable<StreamEvent & { data?: any }>) {
      if (signal?.aborted) break
      if (event.event === 'on_chat_model_stream') {
        const piece = extractTokenText(event)
        if (piece) {
          fullResponse += piece
          await onEvent({ type: 'chunk', content: piece })
        }
      } else if (event.event === 'on_chat_model_end') {
        extractUsage(event, usage)
      }
    }
  }

  try {
    await runStream(llm)
  } catch (e) {
    if (fallbackLLMConfig) {
      const fallbackLLM = createLLMFromConfig(fallbackLLMConfig, { streaming: true })
      await runStream(fallbackLLM)
    } else {
      throw e
    }
  }

  return { rawOutput: fullResponse, usage }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd trip-server && npx vitest run src/services/agent/nodes/__tests__/chatPlanner.test.ts`
Expected: PASS（2 tests）

- [ ] **Step 5: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 6: Commit**

```bash
cd trip-server && git add src/services/agent/nodes/chatPlanner.ts src/services/agent/nodes/__tests__/chatPlanner.test.ts && git commit -m "feat(agent): add chatPlanner node with streaming markdown output"
```

---

### Task 9: chatGraph（chat 路由 + 两条分支）

**Files:**
- Create: `trip-server/src/services/agent/chatGraph.ts`
- Test: `trip-server/src/services/agent/__tests__/chatGraph.test.ts`

**Interfaces:**
- Consumes: `isPlanningRequest` / `researchNode` / `chatPlannerNode` / `PlannerState` + legacy agent（通过 `config.configurable.legacyExecutor` 注入）
- Produces: `buildChatGraph()` → compiled `StateGraph`

- [ ] **Step 1: 写集成测试**

```typescript
// trip-server/src/services/agent/__tests__/chatGraph.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { AgentStreamEvent } from '../../../types/agent'

const mockResearch = vi.fn()
const mockChatPlanner = vi.fn()
const mockLegacyAgent = vi.fn()
const mockBuildAgent = vi.fn()

vi.mock('../nodes/research', () => ({
  researchNode: (...a: any[]) => mockResearch(...a),
}))
vi.mock('../nodes/chatPlanner', () => ({
  chatPlannerNode: (...a: any[]) => mockChatPlanner(...a),
}))

import { buildChatGraph } from '../chatGraph'

function makeConfig(legacyExecutor?: any) {
  const events: AgentStreamEvent[] = []
  return {
    config: {
      configurable: {
        traceRecorder: { add: vi.fn(), flush: vi.fn() },
        onEvent: async (e: AgentStreamEvent) => { events.push(e) },
        signal: undefined,
        stepCounter: { value: 1 },
        llm: {},
        fallbackLLMConfig: null,
        legacyExecutor: legacyExecutor ?? mockLegacyAgent(),
        buildAgent: mockBuildAgent,
      },
    },
    events,
  }
}

function makeState(message: string, city = '北京') {
  return {
    userId: 1, message, city,
    budget: undefined, days: undefined, departureCity: undefined,
    userPreferences: null, conversationHistory: [],
    researchBundle: {}, rawOutput: undefined, parsed: undefined,
    usage: { prompt: 0, completion: 0, total: 0, cached: 0 },
    route: undefined, errors: [],
  } as any
}

describe('chatGraph', () => {
  beforeEach(() => {
    mockResearch.mockReset()
    mockChatPlanner.mockReset()
    mockLegacyAgent.mockReset()
    mockBuildAgent.mockReset()
  })

  it('planning 路由 → research → chatPlanner', async () => {
    mockResearch.mockResolvedValue({ researchBundle: { attractions: 'A' } })
    mockChatPlanner.mockResolvedValue({ rawOutput: '规划完成', usage: { prompt: 0, completion: 0, total: 0, cached: 0 } })
    mockBuildAgent.mockReturnValue({ invoke: vi.fn() })

    const graph = buildChatGraph()
    const { config } = makeConfig()
    await graph.invoke(makeState('帮我规划北京三日游行程'), config)

    expect(mockResearch).toHaveBeenCalledTimes(1)
    expect(mockChatPlanner).toHaveBeenCalledTimes(1)
    expect(mockBuildAgent).not.toHaveBeenCalled()
  })

  it('general 路由 → legacy agent', async () => {
    const legacyExecutor = {
      invoke: vi.fn().mockResolvedValue({ output: '晴天' }),
      streamEvents: async function* () {
        yield { event: 'on_chat_model_stream', data: { chunk: { content: '晴天' } } }
      },
    }
    mockBuildAgent.mockReturnValue(legacyExecutor)

    const graph = buildChatGraph()
    const { config } = makeConfig(legacyExecutor)
    const result = await graph.invoke(makeState('北京今天天气怎么样'), config)

    expect(mockResearch).not.toHaveBeenCalled()
    expect(mockChatPlanner).not.toHaveBeenCalled()
    expect(mockBuildAgent).toHaveBeenCalledTimes(1)
    expect(result.rawOutput).toBeDefined()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd trip-server && npx vitest run src/services/agent/__tests__/chatGraph.test.ts`
Expected: FAIL — `buildChatGraph` 未定义

- [ ] **Step 3: 写实现**

```typescript
// trip-server/src/services/agent/chatGraph.ts
import { StateGraph, END } from '@langchain/langgraph'
import type { RunnableConfig } from '@langchain/core/runnables'
import type { BaseMessage } from '@langchain/core/messages'
import type { StreamEvent } from '@langchain/core/tracers/log_stream'
import { PlannerState } from './state'
import { isPlanningRequest } from './nodes/router'
import { researchNode } from './nodes/research'
import { chatPlannerNode } from './nodes/chatPlanner'
import type { PlannerConfig } from './types'
import type { TokenUsage } from '../../types/agent'

/** 从 city 提取（简单：取消息里的城市关键词，或默认） */
function extractCityFromMessage(message: string): string {
  const cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', '重庆', '南京',
    '天津', '长沙', '苏州', '厦门', '青岛', '大连', '昆明', '三亚', '哈尔滨', '桂林',
    '拉萨', '乌鲁木齐', '贵阳', '南宁', '南昌', '福州', '合肥', '郑州', '济南', '太原', '兰州']
  return cities.find(c => message.includes(c)) ?? '北京'
}

/** legacy agent 节点：用现有 AgentExecutor 跑 streamEvents */
async function legacyAgentNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { onEvent, signal, buildAgent, systemPrompt, conversationHistory } = config.configurable as PlannerConfig & {
    buildAgent: () => Promise<{ streamEvents: (input: any, opts: any) => AsyncIterable<any> }>
    systemPrompt: string
    conversationHistory: BaseMessage[]
  }
  const { HumanMessage } = await import('@langchain/core/messages')
  const executor = await buildAgent()
  const input = { chat_history: [...conversationHistory, new HumanMessage(state.message)] }
  const usage: TokenUsage = { prompt: 0, completion: 0, total: 0, cached: 0 }
  let fullResponse = ''
  let streamEnabled = true

  const eventStream = executor.streamEvents(input, { version: 'v2', signal })
  for await (const event of eventStream as AsyncIterable<StreamEvent & { data?: any }>) {
    if (signal?.aborted) break
    if (event.event === 'on_tool_start') {
      streamEnabled = false
      const name = event.name || 'unknown'
      await onEvent({ type: 'tool_start', name })
    } else if (event.event === 'on_tool_end') {
      fullResponse = ''
      streamEnabled = true
      const name = event.name || 'unknown'
      await onEvent({ type: 'tool_end', name })
    } else if (event.event === 'on_chat_model_stream') {
      const data = event.data
      const chunk = data?.chunk
      const text = chunk?.content
      let piece: string | null = null
      if (typeof text === 'string') piece = text
      else if (Array.isArray(text)) {
        piece = text.map((p: any) => typeof p === 'string' ? p : p?.text ?? '').join('')
      }
      if (piece && streamEnabled) {
        fullResponse += piece
        await onEvent({ type: 'chunk', content: piece })
      }
    } else if (event.event === 'on_chat_model_end') {
      const msg = event.data?.output as { toJSON?: () => { kwargs?: any } } | undefined
      const kwargs = msg?.toJSON?.()?.kwargs as any
      const um = kwargs?.usage_metadata
      const ru = kwargs?.response_metadata?.usage
      if (um) {
        usage.prompt += um.input_tokens ?? 0
        usage.completion += um.output_tokens ?? 0
        usage.total += um.total_tokens ?? (usage.prompt + usage.completion)
        usage.cached += um.input_token_details?.cache_read ?? 0
      } else if (ru) {
        usage.prompt += ru.prompt_tokens ?? 0
        usage.completion += ru.completion_tokens ?? 0
        usage.total += ru.total_tokens ?? (usage.prompt + usage.completion)
        usage.cached += ru.prompt_tokens_details?.cached_tokens ?? ru.prompt_cache_hit_tokens ?? 0
      }
    }
  }

  return { rawOutput: fullResponse, usage }
}

export function buildChatGraph() {
  const graph = new StateGraph(PlannerState)
    .addNode('router', async (state: typeof PlannerState.State) => {
      const route = isPlanningRequest(state.message) ? 'planning' : 'general'
      const city = route === 'planning' ? extractCityFromMessage(state.message) : state.city
      return { route, city }
    })
    .addNode('research', researchNode)
    .addNode('chat_planner', chatPlannerNode)
    .addNode('legacy_agent', legacyAgentNode)

  graph.addEdge('__start__', 'router')
  graph.addConditionalEdges('router', (state: typeof PlannerState.State) => state.route!)
  graph.addEdge('research', 'chat_planner')
  graph.addEdge('chat_planner', END)
  graph.addEdge('legacy_agent', END)

  return graph.compile()
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd trip-server && npx vitest run src/services/agent/__tests__/chatGraph.test.ts`
Expected: PASS（2 tests）

- [ ] **Step 5: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 6: Commit**

```bash
cd trip-server && git add src/services/agent/chatGraph.ts src/services/agent/__tests__/chatGraph.test.ts && git commit -m "feat(agent): add chatGraph with router + planning/general branches"
```

---

### Task 10: agentEngine 改造（接入两个 graph）

**Files:**
- Modify: `trip-server/src/services/agent/agentEngine.ts`

**Interfaces:**
- Consumes: `buildPlannerGraph` / `buildChatGraph` / `PlannerConfig` / 现有 `buildAgent` / `loadUserPreferences` / `loadContext`
- Produces: `AgentEngine.chat()` / `recommend()` 对外签名不变，内部走 graph

- [ ] **Step 1: 改造 `agentEngine.ts`**

关键改动：
1. `recommend()` 内部：构建 `plannerGraph`，准备 `config.configurable`（含 llm / fallbackLLMConfig / traceRecorder / onEvent / stepCounter），invoke graph，取 `state.parsed`，如果 retry 后仍无效则抛错
2. `chat()` 内部：构建 `chatGraph`，准备 `config.configurable`（含 legacyExecutor 构建函数 + systemPrompt + conversationHistory），invoke graph
3. 保留 `buildAgent()` / `processStream()` 供 legacy agent 节点用（`processStream` 逻辑搬到 `legacyAgentNode`，但 `agentEngine` 内保留方法）
4. 保留 `toolCache` / `tools` / `loadUserPreferences` / fallback LLM config 不动

具体改动代码（此处展示 `recommend()` 和 `chat()` 的核心结构，不展开全部）：

```typescript
// agentEngine.ts 核心改动（示意，完整替换 chat/recommend 方法体）

import { buildPlannerGraph } from './plannerGraph'
import { buildChatGraph } from './chatGraph'
import { validateOutput, buildRetryMessage } from './nodes/validate'
import { buildSystemPrompt, buildRecommendSystemPrompt } from './systemPrompt'
import { extractJson } from '../../utils/jsonExtractor'
import { emptyUsage } from './types'
import type { TripContent } from '../../types/agent'

// ... 保留 llm / fallbackLLMConfig / toolCache / tools / loadUserPreferences / buildAgent ...

async chat(params: ChatParams) {
  const { userId, message, conversationId, onEvent, signal, messageId } = params
  const preferences = await this.loadUserPreferences(userId)

  let conversationHistory: BaseMessage[] = []
  let systemSummary: string | null = null
  let conversationRecap: string | null = null
  if (conversationId) {
    const ctx = await loadContext(conversationId)
    systemSummary = ctx.systemSummary
    conversationRecap = ctx.conversationRecap
    conversationHistory = this.dbMessagesToLangChain(ctx.recentMessages)
  }
  const systemPrompt = buildSystemPrompt({
    userPreferences: preferences, conversationSummary: systemSummary, conversationRecap,
  })

  const traceRecorder = new TraceRecorder(messageId)
  const stepCounter = { value: 1 }

  const graph = buildChatGraph()
  const config = {
    configurable: {
      traceRecorder, onEvent, signal, stepCounter,
      llm: this.llm, fallbackLLMConfig: this.fallbackLLMConfig,
      buildAgent: () => this.buildAgent(this.llm!, systemPrompt),
      systemPrompt, conversationHistory,
    },
  }

  const initialState = {
    userId, message, city: '北京', // city 会被 router 覆盖
    budget: undefined, days: undefined, departureCity: undefined,
    userPreferences: preferences, conversationHistory,
    researchBundle: {}, rawOutput: undefined, parsed: undefined,
    usage: emptyUsage(), route: undefined, errors: [],
  }

  try {
    const result = await graph.invoke(initialState, config)
    traceRecorder.add({ step: stepCounter.value++, type: 'complete' })
    await traceRecorder.flush()
    await onEvent({ type: 'complete', content: result.rawOutput ?? '', usage: result.usage })
    return { reply: result.rawOutput ?? '', conversationId }
  } catch (e) {
    const errMsg = e instanceof Error ? e.message : '未知错误'
    traceRecorder.add({ step: stepCounter.value++, type: 'error', error: errMsg })
    await traceRecorder.flush()
    await onEvent({ type: 'error', error: errMsg })
    throw e
  }
}

async recommend(params: RecommendParams): Promise<{ reply: string; parsed: TripContent }> {
  const { userId, city, budget, days, departureCity, onEvent, messageId } = params
  const preferences = await this.loadUserPreferences(userId)

  const traceRecorder = new TraceRecorder(messageId ?? 0)
  const stepCounter = { value: 1 }

  const graph = buildPlannerGraph()
  const config = {
    configurable: {
      traceRecorder, onEvent, signal: undefined, stepCounter,
      llm: this.llm, fallbackLLMConfig: this.fallbackLLMConfig,
    },
  }

  const inputMessage = `请为我规划${departureCity ? `从${departureCity}出发到` : ''}${city}${days}日游行程，预算${budget}元。`

  const initialState = {
    userId, message: inputMessage, city, budget, days, departureCity,
    userPreferences: preferences, conversationHistory: [],
    researchBundle: {}, rawOutput: undefined, parsed: undefined,
    usage: emptyUsage(), route: undefined, errors: [],
  }

  try {
    const result = await graph.invoke(initialState, config)
    // retry 后可能仍无效，二次校验
    if (result.parsed) {
      traceRecorder.add({ step: stepCounter.value++, type: 'complete' })
      await traceRecorder.flush()
      await onEvent({ type: 'complete', content: result.rawOutput ?? '' })
      return { reply: result.rawOutput ?? '', parsed: result.parsed }
    }
    // retry 后仍解析失败
    throw new Error('Agent 多次输出无效 JSON，请稍后重试')
  } catch (e) {
    const errMsg = e instanceof Error ? e.message : '未知错误'
    traceRecorder.add({ step: stepCounter.value++, type: 'error', error: errMsg })
    await traceRecorder.flush()
    await onEvent({ type: 'error', error: errMsg })
    throw e
  }
}
```

- [ ] **Step 2: 删除不再需要的 `processStream` / `invokeWithFallback` 方法**

（`processStream` 逻辑已搬到 `chatPlannerNode` + `legacyAgentNode`，`invokeWithFallback` 逻辑已搬到 `plannerNode`）

- [ ] **Step 3: 验证 tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 跑全部测试**

Run: `cd trip-server && npx vitest run`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
cd trip-server && git add src/services/agent/agentEngine.ts && git commit -m "refactor(agent): integrate plannerGraph + chatGraph into AgentEngine"
```

---

### Task 11: 端到端手动验证

**Files:**
- 无（手动验证）

- [ ] **Step 1: 启动 server**

Run: `cd trip-server && npm run dev`
Expected: 正常启动无报错

- [ ] **Step 2: 测试 recommend 端到端**

用 curl 或前端测试 `/api/trip/recommend`：
```bash
curl -X POST http://localhost:3000/api/trip/recommend \
  -H "Content-Type: application/json" \
  -d '{"city":"北京","budget":3000,"days":2}'
```
Expected: 返回结构化 JSON 行程，含 `dailyItinerary`（2 天）、`budgetBreakdown`（5 项）、`tips`

- [ ] **Step 3: 测试 chat planning 路由**

```bash
curl -X POST http://localhost:3000/api/trip/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"帮我规划北京三日游行程"}'
```
Expected: SSE 流式返回 markdown 行程，含 tool_start/tool_end 事件

- [ ] **Step 4: 测试 chat general 路由**

```bash
curl -X POST http://localhost:3000/api/trip/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"北京今天天气怎么样"}'
```
Expected: 走 legacy agent，调用 `get_weather` 工具，返回天气信息

- [ ] **Step 5: 验证 admin trace 页面**

访问 admin trace 页面，检查 recommend 和 chat 请求的 AgentStep 记录正常落表。

- [ ] **Step 6: 如果全部通过，Commit**

```bash
cd trip-server && git add -A && git commit -m "test(agent): verify e2e recommend + chat flows"
```
（如果有问题，回到对应 task 修复）
