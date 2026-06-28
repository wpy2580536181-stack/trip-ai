const PLANNING_KEYWORDS = ['规划', '行程', '几日游', '攻略', '安排', '路线', '帮我计划', '怎么玩']
// 兼容 "3日"、"3 日"、"3天"、"3 天" 等空格变体
const DAYS_PATTERN = /[\d一二三四五六七八九十两]+\s*(?:日|天)|几日|几天|多少天/
// 多轮修改行程："第二天能加 X 吗"/"第三天改成 Y"/"第一天去掉 Z"
const MODIFY_DAY_PATTERN = /第[一二三四五六七八九十\d]+\s*(?:日|天)/
const MODIFY_INTENT = ['加', '改', '换', '调整', '删', '去掉', '换成', '加上', '安排']

export function isPlanningRequest(message: string): boolean {
  if (!message) return false
  const hasKeyword = PLANNING_KEYWORDS.some(kw => message.includes(kw))
  const hasDays = DAYS_PATTERN.test(message)
  if (hasKeyword && hasDays) return true
  // 多轮修改：含"第N天"+ 修改意图词 → 也算 planning（跟用户协商行程中）
  if (MODIFY_DAY_PATTERN.test(message) && MODIFY_INTENT.some(w => message.includes(w))) return true
  return false
}
