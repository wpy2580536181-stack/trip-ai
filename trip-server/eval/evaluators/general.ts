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
 * ============================================================ */
export function schemaCheck(output: AgentOutput, fixture: Fixture): EvalResult {
  const expected = fixture.expected.json_valid

  // fixture 没规定时不评估
  if (expected === undefined) {
    return { pass: true, reason: 'json_valid not specified, skipping' }
  }

  if (expected === false) {
    // 期望 JSON 无效：output.json 应该是 undefined / null
    if (output.json == null) {
      return { pass: true }
    }
    return {
      pass: false,
      reason: `expected no JSON (json_valid=false) but got valid JSON: ${JSON.stringify(output.json).slice(0, 80)}`,
    }
  }

  // expected=true
  if (output.json == null) {
    return { pass: false, reason: 'expected valid JSON (json_valid=true) but output.json is null' }
  }

  // 用严格的 zod schema 验证（用项目自己的 schema，保证一致性）
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

    // 城市校验
    if (req.city) {
      // 从 output.json 找这个 POI 的 city 字段
      const foundCity = findPoiCity(output, found)
      if (foundCity && !isCityOrNearby(foundCity, req.city)) {
        cityMismatch.push({ poi: req, found: foundCity })
      }
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

/** 从 output 里抽取所有 POI 名（行程 + 文本） */
function extractPoiNames(output: AgentOutput): string[] {
  const names: string[] = []

  // 1. 行程 JSON 里的 spot（适配 TripContentSchema 的 dailyItinerary[].morning/afternoon/evening 结构）
  if (output.json && Array.isArray((output.json as any).dailyItinerary)) {
    for (const day of (output.json as any).dailyItinerary) {
      for (const slot of [day.morning, day.afternoon, day.evening]) {
        if (slot && slot.spot) names.push(slot.spot)
      }
    }
  }

  // 2. 文本里"推荐"列出的 POI（粗略抽取：引号内、书名号内）
  const quoted = output.text.match(/[「『"']([^「『"']{2,20})[」』"']/g) || []
  for (const q of quoted) {
    const inner = q.slice(1, -1).trim()
    if (inner.length >= 2) names.push(inner)
  }

  return names
}

/** 在 output.json 里查找某个 POI 名对应的 city 字段 */
function findPoiCity(output: AgentOutput, poiName: string): string | null {
  if (!output.json || !Array.isArray((output.json as any).dailyItinerary)) return null
  for (const day of (output.json as any).dailyItinerary) {
    for (const slot of [day.morning, day.afternoon, day.evening]) {
      if (slot && slot.spot === poiName) {
        // 优先用 slot.city，否则用顶级 city 字段
        return slot.city || (output.json as any).city || null
      }
    }
  }
  return null
}

/* ============================================================
 * 3. keyword_coverage
 * 验证必含 / 必不含关键词
 * ============================================================ */
export function keywordCoverage(output: AgentOutput, fixture: Fixture): EvalResult {
  const must = fixture.expected.must_contain_keywords || []
  const mustNot = fixture.expected.must_not_contain_keywords || []
  const text = output.text

  const missing = must.filter((kw) => !text.includes(kw))
  const forbidden = mustNot.filter((kw) => text.includes(kw))

  if (missing.length === 0 && forbidden.length === 0) {
    return {
      pass: true,
      details: { mustHit: must.length, mustNotHit: mustNot.length },
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
 * ============================================================ */
export function toolCallAudit(output: AgentOutput, fixture: Fixture): EvalResult {
  const rules = fixture.expected.tool_calls
  if (!rules || rules.length === 0) {
    return { pass: true, reason: 'no tool_calls rules, skipping' }
  }

  const calls = output.toolCalls || []
  const violations: string[] = []

  for (const rule of rules) {
    const count = calls.filter((c) => c.name === rule.name).length
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
 * 适配 TripContentSchema：
 * - 天数 = json.days（顶级 int 字段）
 * - 每天活动 = dailyItinerary[i].morning/afternoon/evening 三个时段
 *   - 每个时段若 .spot 非空则算 1 个活动
 *   - maxPerDay 默认 3（morning/afternoon/evening）
 * ============================================================ */
export function paceConsistency(output: AgentOutput, fixture: Fixture): EvalResult {
  const json = output.json as any
  const expectedDays = fixture.expected.days
  const maxPerDay = fixture.expected.max_activities_per_day

  const violations: string[] = []

  if (expectedDays !== undefined) {
    if (!json || typeof json.days !== 'number') {
      return { pass: false, reason: 'output.json.days 不存在或不是 number' }
    }
    if (json.days !== expectedDays) {
      violations.push(`行程天数 ${json.days} ≠ 期望 ${expectedDays}`)
    }
  }

  if (maxPerDay !== undefined && Array.isArray(json?.dailyItinerary)) {
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

  if (violations.length === 0) {
    return {
      pass: true,
      details: { days: json?.days, maxPerDay, slots: json?.dailyItinerary?.length },
    }
  }
  return { pass: false, reason: violations.join('; ') }
}
