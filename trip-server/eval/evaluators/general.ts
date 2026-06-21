/**
 * 通用 evaluator
 *
 * - schema_check: 验证 JSON 结构合规
 * - poi_city_match: 验证 POI 在期望城市（含 100km 周边）
 * - keyword_coverage: 验证必含/必不含关键词
 * - tool_call_audit: 验证工具调用次数合规
 * - pace_consistency: 验证每天活动数不超限
 */

import type { AgentOutput, EvalResult, Fixture, PoiMatch } from '../types'
import { isCityOrNearby } from '../geo'
import { TripContentSchema } from '../../src/types/agent'

/* ============================================================
 * 1. schema_check
 * 验证 fixture.expected.json_valid 与 output.json 是否一致
 * + 如果 json_valid=true，验证 schema 解析成功
 *
 * 注意：实际 agent 输出是 markdown，不嵌 JSON 代码块。
 * 真实场景下 output.json 通常是 undefined。
 * fixture 的 json_valid 字段更像是"该有结构化数据"的信号，
 * 但我们从 markdown 文本里也能提取结构——所以这步是软校验。
 * ============================================================ */
export function schemaCheck(output: AgentOutput, fixture: Fixture): EvalResult {
  const expected = fixture.expected.json_valid

  if (expected === undefined) {
    return { pass: true, reason: 'json_valid not specified, skipping' }
  }

  if (expected === false) {
    if (output.json == null) {
      return { pass: true }
    }
    return {
      pass: false,
      reason: `expected no JSON (json_valid=false) but got valid JSON: ${JSON.stringify(output.json).slice(0, 80)}`,
    }
  }

  // expected=true
  if (output.json != null) {
    // 有 JSON：用严格 zod schema 验证
    const result = TripContentSchema.safeParse(output.json)
    if (result.success) {
      return { pass: true, details: { days: result.data.days, itineraryDays: result.data.dailyItinerary.length } }
    }
    return {
      pass: false,
      reason: `JSON schema 验证失败: ${result.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')}`,
      details: { zodIssues: result.error.issues },
    }
  }

  // 没 JSON：放宽——text 含"Day N"标记也算 pass
  const hasDayMarkers = /Day\s*\d+|第\s*\d+\s*天/i.test(output.text)
  if (hasDayMarkers) {
    return { pass: true, reason: '无 JSON 但文本含 Day 标记，按结构化输出处理' }
  }
  return { pass: false, reason: 'expected valid JSON or markdown Day markers but got neither' }
}

/* ============================================================
 * 2. poi_city_match
 * 验证 expected.must_contain_pois 里的每个 POI 都在 output 里
 *
 * 匹配规则：
 * - 优先精确匹配 POI name
 * - 否则模糊匹配 name_contains
 * - 城市校验：用 isCityOrNearby（精确或 100km 内）
 * - POI 来源：
 *   a) TripContentSchema 的 days[].slots[].poiName（行程场景）
 *   b) AgentOutput.text 里的"POI 名"出现（兜底，文本里提也算）
 * ============================================================ */
export function poiCityMatch(output: AgentOutput, fixture: Fixture): EvalResult {
  const required = fixture.expected.must_contain_pois
  if (!required || required.length === 0) {
    return { pass: true, reason: 'no must_contain_pois, skipping' }
  }

  // 抽取 output 里所有 POI 名
  const poiNames = extractPoiNames(output)

  const missing: string[] = []
  const cityMismatch: Array<{ poi: PoiMatch; found: string | null }> = []

  for (const req of required) {
    const needle = req.name || req.name_contains
    if (!needle) continue

    const found = poiNames.find(
      (n) => (req.name && n === req.name) || (req.name_contains && n.includes(req.name_contains)),
    )

    if (!found) {
      missing.push(needle)
      continue
    }

    // 城市校验（仅当 JSON 里能找到 city 字段时才校验）
    if (req.city) {
      const foundCity = findPoiCity(output, found)
      if (foundCity && !isCityOrNearby(foundCity, req.city)) {
        cityMismatch.push({ poi: req, found: foundCity })
      }
      // 如果 foundCity 是 null（纯 markdown 场景），跳过 city 校验
    }
  }

  if (missing.length === 0 && cityMismatch.length === 0) {
    return { pass: true, details: { checkedPois: required.length } }
  }

  const reasons: string[] = []
  if (missing.length > 0) {
    reasons.push(`未找到 POI: ${missing.join(', ')}`)
  }
  if (cityMismatch.length > 0) {
    reasons.push(
      `城市不符: ${cityMismatch.map((m) => `${m.poi.name || m.poi.name_contains} 期望 ${m.poi.city} 实际 ${m.found}`).join('; ')}`,
    )
  }
  return { pass: false, reason: reasons.join('; ') }
}

/**
 * 从 output 里抽取所有 POI 名（行程 + 文本）
 *
 * 数据源：
 * 1) JSON dailyItinerary[].*.spot（如果 agent 输出了代码块）
 * 2) Markdown 文本：
 *    - **加粗** 文本（"**人民公园 · 鹤鸣茶社**" → "人民公园 · 鹤鸣茶社"）
 *    - "上午/中午/下午/晚上" 后面紧跟的内容
 *    - 列表项 "- **XXX**" 或 "1. XXX"
 *    - 已有 POI 名（fixtures 里 hardcode 的）
 */
function extractPoiNames(output: AgentOutput): string[] {
  const names: string[] = []

  // 1) JSON 里的 spot
  if (output.json && Array.isArray((output.json as any).dailyItinerary)) {
    for (const day of (output.json as any).dailyItinerary) {
      for (const slot of [day.morning, day.afternoon, day.evening]) {
        if (slot && slot.spot) names.push(slot.spot)
      }
    }
  }

  // 2) Markdown 加粗 **XXX**
  const boldRe = /\*\*([^*]{2,30})\*\*/g
  let m
  while ((m = boldRe.exec(output.text)) !== null) {
    const content = m[1].trim()
    // 过滤掉"非 POI"加粗：纯数字/章节标题/时间等
    if (/^Day\s*\d+/.test(content)) continue
    if (/^第\s*\d+\s*[天日]/.test(content)) continue
    if (/^\d+[.、]/.test(content)) continue
    if (/[0-9]+:00|上午|下午|中午|晚上|清晨|傍晚/.test(content) && !/[一-龥]{4,}/.test(content)) continue
    names.push(content)
  }

  // 3) 时段前缀 "上午/中午/下午/晚上 XXX"
  const slotRe = /(?:上午|中午|下午|晚上|清晨|傍晚)\s*[::]?\s*\*?\*?([^*\n]{2,30})/g
  while ((m = slotRe.exec(output.text)) !== null) {
    const content = m[1].trim().replace(/\*+/g, '').trim()
    // 去掉冒号后的描述
    const cleaned = content.split(/[，。；,;\n]/)[0].trim()
    if (cleaned.length >= 2) names.push(cleaned)
  }

  return [...new Set(names)]
}

/** 在 output.json 里查找某个 POI 名对应的 city 字段 */
function findPoiCity(output: AgentOutput, poiName: string): string | null {
  if (!output.json || !Array.isArray((output.json as any).dailyItinerary)) return null
  for (const day of (output.json as any).dailyItinerary) {
    for (const slot of [day.morning, day.afternoon, day.evening]) {
      if (slot && slot.spot === poiName) {
        return slot.city || (output.json as any).city || null
      }
    }
  }
  return null
}

/* ============================================================
 * 3. keyword_coverage
 * 验证必含 / 必不含关键词
 *
 * 匹配模式（由 fixture.expected.keyword_match_mode 决定，默认 'all'）：
 * - 'all'：所有 must 关键词都必须命中（严格）
 * - 'any'：任一 must 关键词命中即可（宽松，常用于"概念性"关键词组）
 * ============================================================ */
export function keywordCoverage(output: AgentOutput, fixture: Fixture): EvalResult {
  const must = fixture.expected.must_contain_keywords || []
  const mustNot = fixture.expected.must_not_contain_keywords || []
  const mode = (fixture.expected as any).keyword_match_mode || 'all'
  const text = output.text

  let missing: string[]
  if (mode === 'any') {
    // 任一命中即可：missing 是"全部都没命中"时才非空
    const anyHit = must.some((kw) => text.includes(kw))
    missing = anyHit ? [] : must
  } else {
    missing = must.filter((kw) => !text.includes(kw))
  }
  const forbidden = mustNot.filter((kw) => text.includes(kw))

  if (missing.length === 0 && forbidden.length === 0) {
    return {
      pass: true,
      details: { mustHit: must.length, mustNotHit: mustNot.length, mode },
    }
  }

  const reasons: string[] = []
  if (missing.length > 0) {
    reasons.push(`缺少必含关键词: ${missing.join(', ')}`)
  }
  if (forbidden.length > 0) {
    reasons.push(`出现禁用关键词: ${forbidden.join(', ')}`)
  }
  return { pass: false, reason: reasons.join('; ') }
}

/* ============================================================
 * 4. tool_call_audit
 * 验证工具调用 min_calls / max_calls 合规
 *
 * 工具名匹配：大小写不敏感 + 容许下划线/驼峰互换
 * （fixture 写 "getWeather" 实际工具名可能是 "get_weather"）
 * ============================================================ */
function normalizeToolName(name: string): string {
  return name.toLowerCase().replace(/[_-]/g, '')
}

export function toolCallAudit(output: AgentOutput, fixture: Fixture): EvalResult {
  const rules = fixture.expected.tool_calls
  if (!rules || rules.length === 0) {
    return { pass: true, reason: 'no tool_calls rules, skipping' }
  }

  const calls = output.toolCalls || []
  const violations: string[] = []

  for (const rule of rules) {
    const ruleName = normalizeToolName(rule.name)
    const count = calls.filter((c) => normalizeToolName(c.name) === ruleName).length
    if (rule.min_calls !== undefined && count < rule.min_calls) {
      violations.push(`${rule.name} 调用 ${count} 次 < 至少 ${rule.min_calls} 次`)
    }
    if (rule.max_calls !== undefined && count > rule.max_calls) {
      violations.push(`${rule.name} 调用 ${count} 次 > 至多 ${rule.max_calls} 次`)
    }
  }

  if (violations.length === 0) {
    return { pass: true, details: { totalCalls: calls.length } }
  }
  return { pass: false, reason: violations.join('; ') }
}

/* ============================================================
 * 5. pace_consistency
 * 验证 days 数 + 每天活动数不超 max_activities_per_day
 *
 * 数据源：优先 JSON（如果 agent 输出了代码块），其次从 markdown 文本解析
 * - 天数：JSON 顶级 days / 文本里 "Day N" 数量
 * - 每天活动：JSON dailyItinerary[i].morning/afternoon/evening / 文本里 Day N 下的项目数
 * ============================================================ */
export function paceConsistency(output: AgentOutput, fixture: Fixture): EvalResult {
  const expectedDays = fixture.expected.days
  const maxPerDay = fixture.expected.max_activities_per_day
  const json = output.json as any

  const violations: string[] = []

  if (expectedDays !== undefined) {
    let actualDays: number | null = null

    if (json && typeof json.days === 'number') {
      actualDays = json.days
    } else {
      // 从 markdown 文本解析 Day N
      const dayMatches = output.text.match(/(?:Day\s*\d+|第\s*\d+\s*天)/gi)
      if (dayMatches) {
        actualDays = new Set(dayMatches.map((m) => m.toLowerCase().replace(/\s+/g, ''))).size
      }
    }

    if (actualDays === null) {
      return { pass: false, reason: 'output 找不到天数信息（既无 JSON.days 也无 Day N 文本）' }
    }
    if (actualDays !== expectedDays) {
      violations.push(`行程天数 ${actualDays} ≠ 期望 ${expectedDays}`)
    }
  }

  // maxPerDay 检查
  if (maxPerDay !== undefined) {
    if (Array.isArray(json?.dailyItinerary)) {
      for (let i = 0; i < json.dailyItinerary.length; i++) {
        const day = json.dailyItinerary[i]
        const filledSlots = [day.morning, day.afternoon, day.evening].filter(
          (s: any) => s && s.spot && s.spot.length > 0,
        ).length
        if (filledSlots > maxPerDay) {
          violations.push(`Day ${i + 1} 有 ${filledSlots} 个活动 > 上限 ${maxPerDay}`)
        }
      }
    }
    // 文本节奏检查略——LLM markdown 格式太灵活，不强校验
  }

  if (violations.length === 0) {
    return { pass: true, details: { maxPerDay } }
  }
  return { pass: false, reason: violations.join('; ') }
}
