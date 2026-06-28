/**
 * Eval 框架类型定义
 *
 * 一个 fixture = 一个测试用例
 * 一个 evaluator = 一个评分函数
 * Runner 加载所有 fixture，依次跑 evaluator，输出报告
 */

/** Agent 工具调用记录（从 agent trace 提取） */
export interface ToolCall {
  name: string
  args?: Record<string, any>
  result?: any
  timestamp?: string
}

/** Agent 完整输出（runner 收集的产物） */
export interface AgentOutput {
  /** 完整文本响应（含 SSE 流式拼接） */
  text: string
  /** 解析出的 JSON（如有） */
  json?: any
  /** 工具调用列表（按时间顺序） */
  toolCalls: ToolCall[]
  /** 错误（如有） */
  error?: string
  /** token 消耗 */
  tokens?: {
    prompt: number
    completion: number
    total: number
    cached?: number
  }
  /** 响应耗时 ms */
  durationMs?: number
}

/** Fixture expected 中的一种 POI 匹配规则 */
export interface PoiMatch {
  /** 精确匹配 POI 名 */
  name?: string
  /** 模糊匹配 POI 名（包含即可） */
  name_contains?: string
  /** 期望所在城市（可省略，省略时任何城市均可） */
  city?: string
  /** 期望所在城市的"附近"范围（基于 100km 半径） */
  city_nearby?: string
}

/** Fixture 中 tool_calls 的一条规则 */
export interface ToolCallRule {
  name: string
  /** 最少调用次数（0 = 不调用） */
  min_calls?: number
  /** 最多调用次数 */
  max_calls?: number
}

/** Fixture expected 节 */
export interface FixtureExpected {
  /** 必含 POI（name_contains 模糊匹配 + city 校验 + 周边城市放宽） */
  must_contain_pois?: PoiMatch[]
  /** 必含关键词（出现在 text 里） */
  must_contain_keywords?: string[]
  /** 必不含关键词 */
  must_not_contain_keywords?: string[]
  /** 期望天数 */
  days?: number
  /** 期望 JSON 可解析 */
  json_valid?: boolean
  /** 期望是推荐场景（不是行程） */
  is_recommendation?: boolean
  /** 期望是细节问答（不是新行程） */
  is_detail_answer?: boolean
  /** 每天最多活动数（节奏一致性） */
  max_activities_per_day?: number
  /** 工具调用规则 */
  tool_calls?: ToolCallRule[]
  /** 是否每条活动都有 price 字段 */
  activities_have_price_field?: boolean
  /** 是否包含具体价格数字 */
  contains_price_number?: boolean
}

/** Fixture input 节 */
export interface FixtureInput {
  message: string
  preferences?: Record<string, any>
  history?: Array<{ role: 'user' | 'assistant'; content: string; timestamp?: string }>
}

/** 完整 Fixture */
export interface Fixture {
  id: string
  description: string
  tags: string[]
  input: FixtureInput
  expected: FixtureExpected
  evaluators: string[]
}

/** Evaluator 函数签名 */
export type EvaluatorFn = (output: AgentOutput, fixture: Fixture) => EvalResult

/** 单个 evaluator 跑出来的结果 */
export interface EvalResult {
  /** 通过？ */
  pass: boolean
  /** 失败原因（pass=true 时为空） */
  reason?: string
  /** 详细评分（可选，给 LLM judge / 调试用） */
  details?: Record<string, any>
}

/** Fixture 整体跑出来的结果 */
export interface FixtureResult {
  fixtureId: string
  description: string
  tags: string[]
  agentOutput?: AgentOutput
  /** 每个 evaluator 的结果 */
  evaluatorResults: Record<string, EvalResult>
  /** 整体是否通过（所有 evaluator 都 pass） */
  pass: boolean
  /** 跑该 fixture 耗时 ms */
  durationMs: number
  /** 错误信息（fixture 自身跑挂了） */
  error?: string
}

/** 报告总览 */
export interface ReportSummary {
  totalFixtures: number
  passedFixtures: number
  failedFixtures: number
  passRate: number
  totalDurationMs: number
  byTag: Record<string, { total: number; passed: number; passRate: number }>
  byEvaluator: Record<string, { total: number; passed: number; passRate: number }>
  /** Token 累计（仅真实模式有值，mock 模式 undefined） */
  totalTokens?: { prompt: number; completion: number; total: number; cached: number; hitRate: number }
}
