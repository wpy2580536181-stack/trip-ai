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