/**
 * 多轮对话 + 反例 evaluator
 *
 * - destination_override: 跟随最新目的地指令
 * - context_memory: 是否记得上文关键信息
 * - no_forced_itinerary: 不该硬塞完整行程（反例场景）
 */

import type { AgentOutput, EvalResult, Fixture } from '../types'

/* ============================================================
 * 1. destination_override
 * 验证多轮对话中用户改了目的地后，Agent 跟随了最新指令
 *
 * 算法：
 * 1) 从 history 提取最后一轮 user 的"原目的地"（从 POI 关键词反推）
 * 2) 从 input.message 提取"新目的地"（关键词"改成/换成/换/去"+城市）
 * 3) 验证 output.json 里的 POI 都在新目的地城市，不在原目的地
 *
 * 简化策略：直接用 fixture 的 must_contain_pois（应在的城市）+ must_not_contain_keywords（不应在的城市）
 * ============================================================ */
export function destinationOverride(output: AgentOutput, fixture: Fixture): EvalResult {
  // 必须有 history 才算多轮
  if (!fixture.input.history || fixture.input.history.length === 0) {
    return { pass: true, reason: '无 history，非多轮对话，跳过' }
  }

  // must_contain_pois 应该有目标城市的 POI
  const required = fixture.expected.must_contain_pois || []
  const targetCities = new Set(
    required.map((p) => p.city).filter((c): c is string => !!c),
  )

  if (targetCities.size === 0) {
    return { pass: true, reason: 'no target city specified in must_contain_pois, skipping' }
  }

  // 从 must_not_contain_keywords 找"原目的地"线索
  const bannedKeywords = fixture.expected.must_not_contain_keywords || []

  const violations: string[] = []

  // 检查 output.json 里的 POI 是否落在目标城市
  if (output.json && Array.isArray((output.json as any).dailyItinerary)) {
    for (const day of (output.json as any).dailyItinerary) {
      for (const slot of [day.morning, day.afternoon, day.evening]) {
        if (!slot?.spot) continue
        const bannedHit = bannedKeywords.find((kw) => slot.spot.includes(kw))
        if (bannedHit) {
          violations.push(`Day ${day.day} 推荐了原目的地 POI："${slot.spot}"（含"${bannedHit}"），未跟随新指令`)
        }
      }
    }
  }

  // 文本里也检查
  for (const kw of bannedKeywords) {
    if (output.text.includes(kw)) {
      violations.push(`文本中提到原目的地关键词："${kw}"`)
    }
  }

  if (violations.length === 0) {
    return { pass: true, details: { targetCities: [...targetCities] } }
  }
  return { pass: false, reason: violations.join('; ') }
}

/* ============================================================
 * 2. context_memory
 * 验证 Agent 记得上文的某关键信息
 *
 * 算法：
 * 1) 从 history 最后一条 assistant 提取关键实体（POI 名/日期等）
 * 2) 验证 input.message 提到的追问对象在 output.text 里出现
 *
 * 简化策略：用 must_contain_keywords 包含"上文关键实体"
 * 如果 must_contain_keywords 全部命中 → pass（Agent 记得）
 * 否则 fail
 * ============================================================ */
export function contextMemory(output: AgentOutput, fixture: Fixture): EvalResult {
  if (!fixture.input.history || fixture.input.history.length === 0) {
    return { pass: true, reason: '无 history，非多轮对话，跳过' }
  }

  const must = fixture.expected.must_contain_keywords || []
  if (must.length === 0) {
    return { pass: true, reason: 'no must_contain_keywords, skipping' }
  }

  // 检测 must 里是否包含"上文关键词"（用 last assistant 消息校对）
  const lastAssistant = [...fixture.input.history].reverse().find((h) => h.role === 'assistant')
  if (!lastAssistant) {
    return { pass: true, reason: 'no last assistant message, skipping' }
  }

  // 抽取上文 POI 名（粗略：2-10 字的连续中文）
  const upperContextPOIs = lastAssistant.content.match(/[\u4e00-\u9fa5]{2,10}/g) || []

  // 验证 output.text 至少包含 must 中的关键词
  const missing = must.filter((kw) => !output.text.includes(kw))
  if (missing.length === 0) {
    return { pass: true, details: { mustHit: must.length, upperContextPOIs: upperContextPOIs.slice(0, 3) } }
  }
  return { pass: false, reason: `缺失上文关键信息：${missing.join(', ')}` }
}

/* ============================================================
 * 3. no_forced_itinerary
 * 验证 Agent 不该硬塞具体行程（反例场景）
 *
 * 检测：
 * 1) output.json 是 null 或 days 为空（不是硬塞的行程）
 * 2) output.text 不含"Day 1" / "第1天" / "Day 2" 等结构化行程词
 * 3) 必不含 must_not_contain_keywords 里的硬塞关键词
 * ============================================================ */
const ITINERARY_HARDCODE_PATTERNS = [
  /第\s*\d+\s*天/,
  /Day\s*\d+/i,
  /行程安排[:：]/,
  /早上[:：]?\s*[\u4e00-\u9fa5]/,
  /上午[:：]?\s*[\u4e00-\u9fa5]/,
  /下午[:：]?\s*[\u4e00-\u9fa5]/,
  /晚上[:：]?\s*[\u4e00-\u9fa5]/,
]

export function noForcedItinerary(output: AgentOutput, fixture: Fixture): EvalResult {
  // 判断 fixture 是否"反例"：
  // - 没有 expected.days（行程）和 is_recommendation：推荐场景
  // - json_valid=false：非行程输出
  // 注：is_detail_answer（细节问答）不算反例——它可能引用 Day N 是合理的
  const isRejectionFixture =
    (fixture.expected.days === undefined && fixture.expected.is_recommendation !== true) ||
    fixture.expected.json_valid === false ||
    fixture.expected.is_recommendation === true

  if (!isRejectionFixture) {
    return { pass: true, reason: '非反例 fixture，跳过' }
  }

  const violations: string[] = []

  // 1. JSON 行程不该被硬塞
  if (output.json && Array.isArray((output.json as any).dailyItinerary) && (output.json as any).dailyItinerary.length > 0) {
    violations.push(`反例场景却输出了 ${(output.json as any).dailyItinerary.length} 天行程`)
  }

  // 2. 文本里不该有结构化行程词
  for (const pat of ITINERARY_HARDCODE_PATTERNS) {
    if (pat.test(output.text)) {
      violations.push(`反例场景包含硬塞关键词：${pat.source}`)
    }
  }

  // 3. 必不含关键词
  const banned = fixture.expected.must_not_contain_keywords || []
  const bannedHit = banned.filter((kw) => output.text.includes(kw))
  if (bannedHit.length > 0) {
    violations.push(`出现硬塞关键词：${bannedHit.join(', ')}`)
  }

  if (violations.length === 0) {
    return { pass: true }
  }
  return { pass: false, reason: violations.join('; ') }
}
