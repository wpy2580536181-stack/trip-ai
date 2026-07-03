// trip-server/src/services/agent/nodes/validate.ts
import { z } from 'zod'
import { TripContentSchema, type TripContent } from '../../../types/agent'
import { extractJson, extractJsonString } from '../../../utils/jsonExtractor'

/**
 * Level 1: JSON 修复（不消耗 Token）
 * 处理 LLM 常见的 JSON 格式问题，尝试修复后重新 parse。
 * 每步独立 try-catch，确保单步失败不影响其他修复。
 */
export function repairJson(raw: string): string {
  let s = raw

  // 1. 去除 markdown 代码块包裹
  try {
    s = s.replace(/```json\s*/gi, '').replace(/```\s*/g, '')
  } catch { /* 忽略 */ }

  // 2. 找到第一个 { 和最后一个 }，去除首尾多余文字
  try {
    const firstBrace = s.indexOf('{')
    const lastBrace = s.lastIndexOf('}')
    if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
      s = s.slice(firstBrace, lastBrace + 1)
    }
  } catch { /* 忽略 */ }

  // 3. 去除尾逗号: ,] → ]  ,} → }
  try {
    s = s.replace(/,\s*([\]}])/g, '$1')
  } catch { /* 忽略 */ }

  // 4. 仅在文本中没有双引号时，才尝试单引号替换为双引号（保守策略）
  try {
    if (!s.includes('"')) {
      s = replaceSingleQuotes(s)
    }
  } catch { /* 忽略 */ }

  return s
}

/**
 * 将 JSON 字符串中的单引号替换为双引号，同时避免在双引号字符串内部误替换。
 */
function replaceSingleQuotes(s: string): string {
  let result = ''
  let inDouble = false
  let inSingle = false
  let escape = false

  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (escape) {
      result += ch
      escape = false
      continue
    }
    if (ch === '\\') {
      result += ch
      escape = true
      continue
    }
    if (inDouble) {
      result += ch
      if (ch === '"') inDouble = false
      continue
    }
    if (inSingle) {
      if (ch === "'") {
        result += '"'
        inSingle = false
      } else {
        // 单引号字符串内遇到双引号需转义
        result += ch === '"' ? '\\"' : ch
      }
      continue
    }
    // 不在任何字符串内
    if (ch === '"') {
      inDouble = true
      result += ch
    } else if (ch === "'") {
      inSingle = true
      result += '"'
    } else {
      result += ch
    }
  }
  return result
}

/**
 * Level 3: 业务逻辑校验（不阻断，返回警告数组）
 * 警告数量上限 = min(20, days)，超过只保留前 N 条。
 */
export function validateBusinessLogic(parsed: TripContent): string[] {
  const warnings: string[] = []

  // 预算分配合理性：budgetBreakdown 各项之和与 totalBudget 偏差不超过 20%
  const bb = parsed.budgetBreakdown
  const sum = bb.accommodation + bb.food + bb.transportation + bb.tickets + bb.other
  if (parsed.totalBudget > 0) {
    const deviation = Math.abs(sum - parsed.totalBudget) / parsed.totalBudget
    if (deviation > 0.2) {
      warnings.push(
        `预算分配之和(${sum}元)与总预算(${parsed.totalBudget}元)偏差${(deviation * 100).toFixed(0)}%，超过20%阈值`
      )
    }
  }

  // 天数一致性：dailyItinerary 数组长度应与 days 字段匹配
  if (parsed.dailyItinerary.length !== parsed.days) {
    warnings.push(
      `行程天数(${parsed.dailyItinerary.length}天)与声明天数(${parsed.days}天)不一致`
    )
  }

  // 每天至少有一个活动（morning/afternoon/evening 不全为空字符串）
  for (const day of parsed.dailyItinerary) {
    const allEmpty =
      day.morning.spot === '' && day.afternoon.spot === '' && day.evening.spot === ''
    if (allEmpty) {
      warnings.push(`第${day.day}天没有任何活动安排`)
    }
  }

  // 上限控制：避免长行程生成大量警告
  const maxWarnings = Math.min(20, parsed.days)
  if (warnings.length > maxWarnings) {
    return warnings.slice(0, maxWarnings)
  }

  return warnings
}

/**
 * 完整的三级校验流程，返回更丰富的结果供 plannerGraph 使用。
 *
 * Level 1: JSON 解析失败 → repairJson（不消耗 Token）
 * Level 2: Zod Schema 校验失败 → 抛异常（由外层 plannerGraph 处理 LLM 重试）
 * Level 3: 业务逻辑校验 → 附加 warnings（不阻断）
 */
export function validateWithRepair(raw: string): {
  parsed: TripContent
  repaired: boolean
  warnings: string[]
} {
  let repaired = false
  let jsonObj: unknown

  // 先尝试 extractJson + JSON.parse（现有逻辑，处理干净输出）
  try {
    jsonObj = extractJson(raw)
  } catch (extractError) {
    // Level 1: JSON 解析失败 → repairJson 后重试（不消耗 Token）
    repaired = true
    try {
      const jsonString = extractJsonString(raw)
      const repairedStr = repairJson(jsonString)
      jsonObj = JSON.parse(repairedStr)
    } catch (repairError) {
      // repairJson 也无法修复，抛出原始 extractJson 的错误
      const repairMsg = repairError instanceof Error ? repairError.message : String(repairError)
      const extractMsg = extractError instanceof Error ? extractError.message : String(extractError)
      throw new Error(`JSON 修复失败: ${repairMsg} (原始错误: ${extractMsg})`)
    }
  }

  // Level 2: Zod Schema 校验 — 失败时抛带 field path 的异常，由外层 plannerGraph 处理 LLM 重试
  try {
    const parsed = TripContentSchema.parse(jsonObj)

    // Level 3: 业务逻辑校验（不阻断）
    const warnings = validateBusinessLogic(parsed)
    if (warnings.length > 0) {
      parsed.warnings = [...(parsed.warnings ?? []), ...warnings]
    }

    return { parsed, repaired, warnings }
  } catch (zodError) {
    if (zodError instanceof z.ZodError) {
      // 格式化 Zod 错误，附带 field path 帮助 LLM 定位问题
      const details = zodError.issues
        .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
        .join('\n')
      throw new Error(`Schema 校验失败:\n${details}`)
    }
    // 非 Zod 错误（如 JSON.parse 的 SyntaxError），直接重抛
    throw zodError
  }
}

export function validateOutput(raw: string): { parsed: TripContent } {
  const { parsed } = validateWithRepair(raw)
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
