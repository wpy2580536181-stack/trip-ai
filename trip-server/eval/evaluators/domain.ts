/**
 * 领域 evaluator
 *
 * - pet_constraint_check: 宠物友好场所校验
 * - dietary_constraint_check: 饮食禁忌校验
 * - weather_adaptation_check: 天气应对校验
 * - budget_field_present: 预算字段完整性
 * - kid_friendly_check: 亲子友好校验
 */

import type { AgentOutput, EvalResult, Fixture } from '../types'

/* ============================================================
 * 1. pet_constraint_check
 * 验证行程里没有宠物禁入场所 + 提到宠物注意事项
 *
 * 检查项：
 * 1) 必含宠物相关关键词（"宠物"或"牵引绳"等）至少 1 个
 * 2) 必不含禁入关键词（动物园、博物馆、餐厅等）
 * 3) 行程中所有 POI 都不是"宠物禁入"类
 * ============================================================ */

/** 宠物禁入场所关键词（出现在 POI 名/活动名中即视为推荐了该场所） */
const PET_BANNED_KEYWORDS = [
  '动物园',
  '野生动物园',
  '水族馆',
  '海洋馆',
  '美术馆',
  '科技馆',
  '展览馆',
  // 注：博物馆/餐厅/酒店 不在列——行程可能合理推荐吃饭/住宿，
  // 真正的"宠物禁入"是动作（"入住普通酒店带宠物"），不是 POI 名
]

const PET_REQUIRED_KEYWORDS = ['宠物', '牵引绳', '防疫', '便便', '狗证', '宠物友好', '遛狗']

export function petConstraintCheck(output: AgentOutput, fixture: Fixture): EvalResult {
  // 1. fixture 里是否提到宠物？没有就跳过
  const message = fixture.input.message
  const mentionsPet = /宠物|狗|猫|金毛|柯基|泰迪|边牧|拉布拉多|萨摩|哈士奇|比熊|贵宾/i.test(message)
  if (!mentionsPet) {
    return { pass: true, reason: '用户没提宠物，跳过' }
  }

  const text = output.text
  const violations: string[] = []

  // 2. 必含宠物提示
  const hasPetTip = PET_REQUIRED_KEYWORDS.some((kw) => text.includes(kw))
  if (!hasPetTip) {
    violations.push(`未提示宠物注意事项（缺少关键词：${PET_REQUIRED_KEYWORDS.slice(0, 3).join('/')} 等）`)
  }

  // 3. 禁入场所
  const bannedHit = PET_BANNED_KEYWORDS.filter((kw) => text.includes(kw))
  if (bannedHit.length > 0) {
    violations.push(`推荐了宠物禁入场所：${bannedHit.join(', ')}`)
  }

  // 4. JSON 行程里也要检查 POI 名（如果有）
  if (output.json && Array.isArray((output.json as any).dailyItinerary)) {
    for (const day of (output.json as any).dailyItinerary) {
      for (const slot of [day.morning, day.afternoon, day.evening]) {
        if (!slot?.spot) continue
        const hit = PET_BANNED_KEYWORDS.find((kw) => slot.spot.includes(kw))
        if (hit) {
          violations.push(`Day ${day.day} 推荐了宠物禁入 POI："${slot.spot}"（含"${hit}"）`)
        }
      }
    }
  }
  // 纯文本场景：上面第 3 步已用 text 覆盖

  if (violations.length === 0) {
    return { pass: true }
  }
  return { pass: false, reason: violations.join('; ') }
}

/* ============================================================
 * 2. dietary_constraint_check
 * 验证饮食禁忌合规
 *
 * 检查项：
 * 1) 必含禁忌相关提示（如"清真"/"素食"/"无麸质"）
 * 2) 必不含禁忌食材关键词
 * ============================================================ */

const DIETARY_RULES: Record<string, { required: string[]; banned: string[]; label: string }> = {
  halal: {
    label: '清真',
    required: ['清真'],
    banned: ['猪肉', '培根', '火腿', '香肠', '烤肠', '猪骨', '猪蹄', '烤鸭', '涮羊肉', '全聚德', '便宜坊'],
  },
  vegetarian: {
    label: '素食',
    required: ['素食', '素菜', '斋饭'],
    banned: ['牛肉', '羊肉', '鸡肉', '猪肉', '鱼', '虾', '蟹'],
  },
  vegan: {
    label: '纯素',
    required: ['素食', '纯素', '植物'],
    banned: ['牛奶', '鸡蛋', '奶酪', '黄油', '蜂蜜', '牛肉', '猪肉'],
  },
  glutenfree: {
    label: '无麸质',
    required: ['无麸质', '面筋'],
    banned: ['面条', '面包', '馒头', '包子', '饺子皮'],
  },
}

export function dietaryConstraintCheck(output: AgentOutput, fixture: Fixture): EvalResult {
  const message = fixture.input.message
  const detected: string[] = []

  // 分别检测每种饮食禁忌
  if (/穆斯林|清真|halal/i.test(message)) {
    detected.push('halal')
  }
  if (/纯素|vegan/i.test(message)) {
    detected.push('vegan')
  } else if (/素食|不吃肉|吃素/i.test(message)) {
    detected.push('vegetarian')
  }
  if (/无麸质|麸质过敏|gluten/i.test(message)) {
    detected.push('glutenfree')
  }

  if (detected.length === 0) {
    return { pass: true, reason: '用户没提饮食禁忌，跳过' }
  }

  const text = output.text
  const violations: string[] = []

  for (const key of detected) {
    const rule = DIETARY_RULES[key]
    const hasRequired = rule.required.some((kw) => text.includes(kw))
    if (!hasRequired) {
      violations.push(`未明确提到"${rule.label}"相关（缺少：${rule.required.join('/')}）`)
    }
    const bannedHit = rule.banned.filter((kw) => text.includes(kw))
    if (bannedHit.length > 0) {
      violations.push(`行程含 ${rule.label} 禁忌食材：${bannedHit.join(', ')}`)
    }
  }

  if (violations.length === 0) {
    return { pass: true, details: { detectedRules: detected } }
  }
  return { pass: false, reason: violations.join('; ') }
}

/* ============================================================
 * 3. weather_adaptation_check
 * 验证天气应对合规
 *
 * 检查项：
 * 1) 必含天气查询工具调用（getWeather）
 * 2) 必含"雨/雪/室内/备选"等应对关键词
 * 3) 必不含"户外/露天"等不当推荐（除非"室内活动"上下文）
 * ============================================================ */

const WEATHER_BAD_KEYWORDS = ['露天', '草坪', '野餐', '露营', '骑行环湖', '冲浪', '日光浴']

export function weatherAdaptationCheck(output: AgentOutput, fixture: Fixture): EvalResult {
  const message = fixture.input.message
  const mentionsWeather = /雨|雪|台风|高温|寒冷|雾霾|沙尘|暴晒/i.test(message)
  if (!mentionsWeather) {
    return { pass: true, reason: '用户没提天气状况，跳过' }
  }

  const text = output.text
  const violations: string[] = []

  // 1. 必含应对关键词
  const hasAdaptation = /雨|雪|室内|备选|避雨|防寒|防晒|防雾霾/.test(text)
  if (!hasAdaptation) {
    violations.push('未提供天气应对方案')
  }

  // 2. 必不含露天推荐
  const badHit = WEATHER_BAD_KEYWORDS.filter((kw) => {
    // 包含"室内"上下文的允许
    const idx = text.indexOf(kw)
    if (idx === -1) return false
    const ctx = text.slice(Math.max(0, idx - 20), idx + kw.length + 20)
    return !/室内|改|避|不推荐|避免|建议改/.test(ctx)
  })
  if (badHit.length > 0) {
    violations.push(`推荐了露天活动（与天气不符）：${badHit.join(', ')}`)
  }

  // 3. 应调用 getWeather 工具
  const calls = output.toolCalls || []
  const weatherCall = calls.find((c) => c.name === 'getWeather')
  if (!weatherCall) {
    violations.push('未调用 getWeather 工具查询实际天气')
  }

  if (violations.length === 0) {
    return { pass: true, details: { weatherCall: !!weatherCall } }
  }
  return { pass: false, reason: violations.join('; ') }
}

/* ============================================================
 * 4. budget_field_present
 * 验证每个时段 slot 都有 ticket 字段（含价格信息）
 * （TripContentSchema 的 slot.ticket 是 string，约定含 "￥xx" 视为含价格）
 * ============================================================ */
export function budgetFieldPresent(output: AgentOutput, fixture: Fixture): EvalResult {
  if (!fixture.expected.activities_have_price_field) {
    return { pass: true, reason: 'fixture 未要求 price 字段，跳过' }
  }

  const json = output.json as any
  if (!json || !Array.isArray(json.dailyItinerary)) {
    return { pass: false, reason: 'output.json.dailyItinerary 不存在' }
  }

  const missing: string[] = []
  for (let i = 0; i < json.dailyItinerary.length; i++) {
    for (const [period, slot] of [
      ['morning', json.dailyItinerary[i].morning],
      ['afternoon', json.dailyItinerary[i].afternoon],
      ['evening', json.dailyItinerary[i].evening],
    ]) {
      if (!slot?.spot) continue
      const ticket = slot.ticket || ''
      if (!ticket || !/￥|¥|元|\d+\s*元/.test(ticket)) {
        missing.push(`Day ${i + 1} ${period}（${slot.spot}）`)
      }
    }
  }

  if (missing.length === 0) {
    return { pass: true }
  }
  return {
    pass: false,
    reason: `以下时段缺价格：${missing.slice(0, 5).join('; ')}${missing.length > 5 ? ` 等 ${missing.length} 项` : ''}`,
  }
}

/* ============================================================
 * 5. kid_friendly_check
 * 验证亲子适配：体力约束 + 必含儿童相关提示
 * ============================================================ */

const KID_BAD_KEYWORDS = ['徒步', '登山', '攀岩', '蹦极', '夜店', '通宵', '潜水', '跳伞', '飙车', '鬼屋']

export function kidFriendlyCheck(output: AgentOutput, fixture: Fixture): EvalResult {
  const message = fixture.input.message
  const mentionsKid = /孩子|小孩|宝宝|儿子|女儿|亲子|带.+岁|家庭/.test(message)
  if (!mentionsKid) {
    return { pass: true, reason: '用户没提孩子，跳过' }
  }

  const text = output.text
  const violations: string[] = []

  // 1. 必含儿童相关提示
  const hasKidTip = /儿童|孩子|亲子|家长|安全|休息|午休|体力/.test(text)
  if (!hasKidTip) {
    violations.push('未提示儿童注意事项')
  }

  // 2. 必不含儿童不宜
  const badHit = KID_BAD_KEYWORDS.filter((kw) => text.includes(kw))
  if (badHit.length > 0) {
    violations.push(`推荐了儿童不宜活动：${badHit.join(', ')}`)
  }

  // 3. JSON 行程里也要检查
  if (output.json && Array.isArray((output.json as any).dailyItinerary)) {
    for (const day of (output.json as any).dailyItinerary) {
      for (const slot of [day.morning, day.afternoon, day.evening]) {
        if (!slot?.spot) continue
        const hit = KID_BAD_KEYWORDS.find((kw) => slot.spot.includes(kw))
        if (hit) {
          violations.push(`Day ${day.day} 推荐了儿童不宜 POI："${slot.spot}"`)
        }
      }
    }
  }

  if (violations.length === 0) {
    return { pass: true }
  }
  return { pass: false, reason: violations.join('; ') }
}
