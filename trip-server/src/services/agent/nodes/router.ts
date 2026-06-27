const PLANNING_KEYWORDS = ['规划', '行程', '几日游', '攻略', '安排', '路线', '帮我计划', '怎么玩']
const DAYS_PATTERN = /[\d一二三四五六七八九十两]+\s*日|几日|几天|多少天/

export function isPlanningRequest(message: string): boolean {
  if (!message) return false
  const hasKeyword = PLANNING_KEYWORDS.some(kw => message.includes(kw))
  const hasDays = DAYS_PATTERN.test(message)
  return hasKeyword && hasDays
}
