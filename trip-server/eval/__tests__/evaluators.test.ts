/**
 * Evaluator 单元测试
 *
 * 每个 evaluator 必须有正/反两路测试。
 * 正向：构造一个"应该 pass"的 AgentOutput，验证 pass=true
 * 反向：构造一个"应该 fail"的 AgentOutput，验证 pass=false 且 reason 正确
 */

import { describe, it, expect } from 'vitest'
import {
  schemaCheck,
  poiCityMatch,
  keywordCoverage,
  toolCallAudit,
  paceConsistency,
} from '../evaluators/general'
import {
  petConstraintCheck,
  dietaryConstraintCheck,
  weatherAdaptationCheck,
  budgetFieldPresent,
  kidFriendlyCheck,
} from '../evaluators/domain'
import {
  destinationOverride,
  contextMemory,
  noForcedItinerary,
} from '../evaluators/multi-turn'
import { isCityOrNearby, cityDistanceKm } from '../geo'
import type { AgentOutput, Fixture } from '../types'

/* ============================================================
 * 测试辅助：构造 AgentOutput
 * ============================================================ */
function makeOutput(overrides: Partial<AgentOutput> = {}): AgentOutput {
  return {
    text: '',
    json: undefined,
    toolCalls: [],
    ...overrides,
  }
}

function makeFixture(overrides: Partial<Fixture> = {}): Fixture {
  return {
    id: 'test-fixture',
    description: 'test',
    tags: [],
    input: { message: 'test' },
    expected: {},
    evaluators: [],
    ...overrides,
  }
}

/* ============================================================
 * geo.ts
 * ============================================================ */
describe('geo', () => {
  it('isCityOrNearby 同名返回 true', () => {
    expect(isCityOrNearby('成都', '成都')).toBe(true)
  })

  it('isCityOrNearby 都江堰算成都周边（~50km）', () => {
    expect(isCityOrNearby('都江堰', '成都')).toBe(true)
  })

  it('isCityOrNearby 峨眉山超出 100km 算 false', () => {
    expect(isCityOrNearby('峨眉山', '成都')).toBe(false)
  })

  it('isCityOrNearby 未登记城市返回 false', () => {
    expect(isCityOrNearby('火星城', '成都')).toBe(false)
  })

  it('cityDistanceKm 上海-苏州约 85km', () => {
    const d = cityDistanceKm('上海', '苏州')
    expect(d).not.toBeNull()
    expect(d!).toBeGreaterThan(80)
    expect(d!).toBeLessThan(90)
  })
})

/* ============================================================
 * schemaCheck
 * ============================================================ */
describe('schemaCheck', () => {
  const validJson = {
    city: '成都',
    days: 1,
    totalBudget: 1000,
    dailyItinerary: [
      {
        day: 1,
        morning: { spot: '宽窄巷子' },
        afternoon: { spot: '锦里' },
        evening: { spot: '火锅' },
      },
    ],
    budgetBreakdown: {
      accommodation: 300,
      food: 300,
      transportation: 100,
      tickets: 200,
      other: 100,
    },
    tips: ['多喝水'],
  }

  it('expected=undefined 时跳过', () => {
    expect(schemaCheck(makeOutput(), makeFixture()).pass).toBe(true)
  })

  it('expected=true 且 JSON 有效 → pass', () => {
    const out = makeOutput({ json: validJson })
    const f = makeFixture({ expected: { json_valid: true } })
    expect(schemaCheck(out, f).pass).toBe(true)
  })

  it('expected=true 但 JSON 缺 days → fail', () => {
    const out = makeOutput({ json: { foo: 'bar' } })
    const f = makeFixture({ expected: { json_valid: true } })
    expect(schemaCheck(out, f).pass).toBe(false)
  })

  it('expected=false 但有 JSON → fail', () => {
    const out = makeOutput({ json: validJson })
    const f = makeFixture({ expected: { json_valid: false } })
    expect(schemaCheck(out, f).pass).toBe(false)
  })

  it('expected=false 且无 JSON → pass', () => {
    const out = makeOutput()
    const f = makeFixture({ expected: { json_valid: false } })
    expect(schemaCheck(out, f).pass).toBe(true)
  })
})

/* ============================================================
 * poiCityMatch
 * ============================================================ */
describe('poiCityMatch', () => {
  it('没规定 must_contain_pois → pass', () => {
    expect(poiCityMatch(makeOutput(), makeFixture()).pass).toBe(true)
  })

  it('JSON 里 name_contains 命中 → pass', () => {
    const out = makeOutput({
      json: { city: '成都', dailyItinerary: [{ day: 1, morning: { spot: '宽窄巷子景区' } }] },
    })
    const f = makeFixture({
      expected: { must_contain_pois: [{ name_contains: '宽窄巷子', city: '成都' }] },
    })
    expect(poiCityMatch(out, f).pass).toBe(true)
  })

  it('JSON 里 POI 缺 city 字段 → pass（无法校验）', () => {
    const out = makeOutput({
      json: { city: '上海', dailyItinerary: [{ day: 1, morning: { spot: '外滩' } }] },
    })
    const f = makeFixture({
      expected: { must_contain_pois: [{ name_contains: '外滩', city: '上海' }] },
    })
    expect(poiCityMatch(out, f).pass).toBe(true)
  })

  it('POI 城市不符（上海 vs 成都）→ fail', () => {
    const out = makeOutput({
      json: {
        city: '上海',
        dailyItinerary: [{ day: 1, morning: { spot: '外滩', city: '上海' } }],
      },
    })
    const f = makeFixture({
      expected: { must_contain_pois: [{ name_contains: '外滩', city: '成都' }] },
    })
    const r = poiCityMatch(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('城市不符')
  })

  it('POI 落在周边城市（如都江堰对成都）→ pass', () => {
    const out = makeOutput({
      json: {
        city: '都江堰',
        dailyItinerary: [{ day: 1, morning: { spot: '都江堰景区', city: '都江堰' } }],
      },
    })
    const f = makeFixture({
      expected: { must_contain_pois: [{ name_contains: '都江堰', city: '成都' }] },
    })
    expect(poiCityMatch(out, f).pass).toBe(true)
  })

  it('POI 完全没出现 → fail', () => {
    const out = makeOutput({
      json: { city: '杭州', dailyItinerary: [{ day: 1, morning: { spot: '西湖' } }] },
    })
    const f = makeFixture({
      expected: { must_contain_pois: [{ name_contains: '兵马俑' }] },
    })
    expect(poiCityMatch(out, f).pass).toBe(false)
  })
})

/* ============================================================
 * keywordCoverage
 * ============================================================ */
describe('keywordCoverage', () => {
  it('必含关键词都命中 → pass', () => {
    const out = makeOutput({ text: '推荐宽窄巷子和锦里，美食必吃火锅' })
    const f = makeFixture({
      expected: { must_contain_keywords: ['宽窄巷子', '火锅'] },
    })
    expect(keywordCoverage(out, f).pass).toBe(true)
  })

  it('缺必含关键词 → fail', () => {
    const out = makeOutput({ text: '推荐宽窄巷子' })
    const f = makeFixture({
      expected: { must_contain_keywords: ['宽窄巷子', '火锅'] },
    })
    const r = keywordCoverage(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('火锅')
  })

  it('出现禁用关键词 → fail', () => {
    const out = makeOutput({ text: '推荐蹦极 + 火锅' })
    const f = makeFixture({
      expected: { must_not_contain_keywords: ['蹦极'] },
    })
    const r = keywordCoverage(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('蹦极')
  })

  it('无关键词规则 → pass', () => {
    expect(keywordCoverage(makeOutput(), makeFixture()).pass).toBe(true)
  })
})

/* ============================================================
 * toolCallAudit
 * ============================================================ */
describe('toolCallAudit', () => {
  it('min_calls 1 但调用 0 次 → fail', () => {
    const out = makeOutput({ toolCalls: [] })
    const f = makeFixture({
      expected: { tool_calls: [{ name: 'retrieve_knowledge', min_calls: 1 }] },
    })
    expect(toolCallAudit(out, f).pass).toBe(false)
  })

  it('min_calls 1 调用 2 次 → pass', () => {
    const out = makeOutput({
      toolCalls: [
        { name: 'retrieve_knowledge' },
        { name: 'retrieve_knowledge' },
      ],
    })
    const f = makeFixture({
      expected: { tool_calls: [{ name: 'retrieve_knowledge', min_calls: 1 }] },
    })
    expect(toolCallAudit(out, f).pass).toBe(true)
  })

  it('max_calls 0 但调用 1 次 → fail', () => {
    const out = makeOutput({ toolCalls: [{ name: 'getWeather' }] })
    const f = makeFixture({
      expected: { tool_calls: [{ name: 'getWeather', max_calls: 0 }] },
    })
    expect(toolCallAudit(out, f).pass).toBe(false)
  })
})

/* ============================================================
 * paceConsistency
 * ============================================================ */
describe('paceConsistency', () => {
  it('天数不符 → fail', () => {
    const out = makeOutput({
      json: { days: 2, dailyItinerary: [{ day: 1 }, { day: 2 }] },
    })
    const f = makeFixture({ expected: { days: 3 } })
    expect(paceConsistency(out, f).pass).toBe(false)
  })

  it('都符合 → pass', () => {
    const out = makeOutput({
      json: {
        days: 2,
        dailyItinerary: [
          { day: 1, morning: { spot: 'A' } },
          { day: 2, morning: { spot: 'B' } },
        ],
      },
    })
    const f = makeFixture({ expected: { days: 2 } })
    expect(paceConsistency(out, f).pass).toBe(true)
  })

  it('每个时段都填满但 maxPerDay=2 → fail', () => {
    const out = makeOutput({
      json: {
        days: 1,
        dailyItinerary: [
          {
            day: 1,
            morning: { spot: 'A' },
            afternoon: { spot: 'B' },
            evening: { spot: 'C' },
          },
        ],
      },
    })
    const f = makeFixture({ expected: { days: 1, max_activities_per_day: 2 } })
    expect(paceConsistency(out, f).pass).toBe(false)
  })
})

/* ============================================================
 * petConstraintCheck
 * ============================================================ */
describe('petConstraintCheck', () => {
  it('用户没提宠物 → pass（跳过）', () => {
    const f = makeFixture({ input: { message: '成都 3 天' } })
    expect(petConstraintCheck(makeOutput(), f).pass).toBe(true)
  })

  it('用户带金毛 + Agent 提到牵引绳 + 无禁入场所 → pass', () => {
    const f = makeFixture({ input: { message: '我带金毛去上海 2 天' } })
    const out = makeOutput({ text: '推荐外滩遛狗，请牵好牵引绳，注意防疫。' })
    expect(petConstraintCheck(out, f).pass).toBe(true)
  })

  it('用户带金毛 + Agent 推荐动物园 → fail', () => {
    const f = makeFixture({ input: { message: '我带金毛去上海 2 天' } })
    const out = makeOutput({ text: '推荐上海动物园，请牵好牵引绳。' })
    const r = petConstraintCheck(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('动物园')
  })

  it('JSON 里推荐了美术馆 → fail', () => {
    const f = makeFixture({ input: { message: '我带金毛去上海 2 天' } })
    const out = makeOutput({
      text: '请牵好牵引绳',
      json: { city: '上海', dailyItinerary: [{ day: 1, morning: { spot: '上海美术馆' } }] },
    })
    const r = petConstraintCheck(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('美术馆')
  })
})

/* ============================================================
 * dietaryConstraintCheck
 * ============================================================ */
describe('dietaryConstraintCheck', () => {
  it('用户没提饮食禁忌 → pass（跳过）', () => {
    const f = makeFixture({ input: { message: '成都 3 天' } })
    expect(dietaryConstraintCheck(makeOutput(), f).pass).toBe(true)
  })

  it('用户说清真 + Agent 推荐牛街清真餐厅 + 无猪肉 → pass', () => {
    const f = makeFixture({ input: { message: '我是穆斯林，3 天北京' } })
    const out = makeOutput({ text: '推荐牛街清真餐厅，鸿宾楼等都是清真美食。' })
    expect(dietaryConstraintCheck(out, f).pass).toBe(true)
  })

  it('用户说清真 + Agent 推荐烤鸭含猪肉 → fail', () => {
    const f = makeFixture({ input: { message: '我是穆斯林，3 天北京' } })
    const out = makeOutput({ text: '推荐烤鸭、涮羊肉、清真小吃' })
    const r = dietaryConstraintCheck(out, f)
    expect(r.pass).toBe(false)
  })

  it('用户说清真 + Agent 在避免语境提"猪肉"（"无猪肉"/"避免猪肉"）→ pass', () => {
    const f = makeFixture({ input: { message: '我是穆斯林，3 天北京' } })
    const out = makeOutput({
      text: '行程承诺全程无猪肉、避免猪肉相关推荐，只去清真餐厅。',
    })
    const r = dietaryConstraintCheck(out, f)
    expect(r.pass).toBe(true)
  })

  it('用户说清真 + Agent 混合"推荐清真"+ 顺带提"避免猪肉" → pass', () => {
    const f = makeFixture({ input: { message: '我是穆斯林，3 天北京' } })
    const out = makeOutput({
      text: '推荐牛街清真餐厅、鸿宾楼。已避免猪肉相关。',
    })
    expect(dietaryConstraintCheck(out, f).pass).toBe(true)
  })

  it('用户说清真 + Agent 提"全聚德已排除" → pass', () => {
    const f = makeFixture({ input: { message: '我是穆斯林，3 天北京' } })
    const out = makeOutput({
      text: '推荐牛街清真餐厅。⚠️ 注意：四季民福、全聚德等烤鸭店未标注清真，我已帮你排除。',
    })
    expect(dietaryConstraintCheck(out, f).pass).toBe(true)
  })
})

/* ============================================================
 * weatherAdaptationCheck
 * ============================================================ */
describe('weatherAdaptationCheck', () => {
  it('用户没提天气 → pass（跳过）', () => {
    const f = makeFixture({ input: { message: '杭州 2 天' } })
    expect(weatherAdaptationCheck(makeOutput(), f).pass).toBe(true)
  })

  it('用户说下雨 + Agent 提到室内 + 调 getWeather → pass', () => {
    const f = makeFixture({ input: { message: '下周去杭州 2 天一直下雨' } })
    const out = makeOutput({
      text: '雨天推荐室内博物馆、灵隐寺。备选方案已准备好。',
      toolCalls: [{ name: 'getWeather' }],
    })
    expect(weatherAdaptationCheck(out, f).pass).toBe(true)
  })

  it('用户说下雨 + Agent 推荐露天草坪 → fail', () => {
    const f = makeFixture({ input: { message: '下周去杭州 2 天一直下雨' } })
    const out = makeOutput({
      text: '推荐户外活动，草坪野餐适合雨天。',
      toolCalls: [{ name: 'getWeather' }],
    })
    const r = weatherAdaptationCheck(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('草坪')
  })

  it('用户说下雨但 Agent 没调 getWeather → fail', () => {
    const f = makeFixture({ input: { message: '下周去杭州 2 天一直下雨' } })
    const out = makeOutput({ text: '雨天推荐室内活动，备选方案已准备。' })
    const r = weatherAdaptationCheck(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('getWeather')
  })
})

/* ============================================================
 * budgetFieldPresent
 * ============================================================ */
describe('budgetFieldPresent', () => {
  it('没要求 price → pass（跳过）', () => {
    expect(budgetFieldPresent(makeOutput(), makeFixture()).pass).toBe(true)
  })

  it('每个 slot 都有 ticket 含价格 → pass', () => {
    const out = makeOutput({
      json: {
        dailyItinerary: [
          {
            day: 1,
            morning: { spot: 'A', ticket: '￥50' },
            afternoon: { spot: 'B', ticket: '￥30' },
          },
        ],
      },
    })
    const f = makeFixture({ expected: { activities_have_price_field: true } })
    expect(budgetFieldPresent(out, f).pass).toBe(true)
  })

  it('有 slot 缺 ticket → fail', () => {
    const out = makeOutput({
      json: {
        dailyItinerary: [
          {
            day: 1,
            morning: { spot: 'A', ticket: '￥50' },
            afternoon: { spot: 'B' },
          },
        ],
      },
    })
    const f = makeFixture({ expected: { activities_have_price_field: true } })
    const r = budgetFieldPresent(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('B')
  })
})

/* ============================================================
 * kidFriendlyCheck
 * ============================================================ */
describe('kidFriendlyCheck', () => {
  it('用户没提孩子 → pass（跳过）', () => {
    const f = makeFixture({ input: { message: '西安 2 天' } })
    expect(kidFriendlyCheck(makeOutput(), f).pass).toBe(true)
  })

  it('用户带 6 岁孩子 + Agent 提到儿童休息 → pass', () => {
    const f = makeFixture({ input: { message: '带 6 岁小孩去西安 2 天' } })
    const out = makeOutput({ text: '行程轻松，儿童需午休。推荐兵马俑。' })
    expect(kidFriendlyCheck(out, f).pass).toBe(true)
  })

  it('用户带 6 岁孩子 + Agent 推荐登山 → fail', () => {
    const f = makeFixture({ input: { message: '带 6 岁小孩去西安 2 天' } })
    const out = makeOutput({ text: '推荐登山、华山徒步。儿童需午休。' })
    const r = kidFriendlyCheck(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('登山')
  })
})

/* ============================================================
 * destinationOverride
 * ============================================================ */
describe('destinationOverride', () => {
  it('无 history → pass（跳过）', () => {
    const f = makeFixture({ input: { message: '改成重庆' } })
    expect(destinationOverride(makeOutput(), f).pass).toBe(true)
  })

  it('多轮改目的地 + Agent 跟随新指令 → pass', () => {
    const f = makeFixture({
      input: {
        message: '那改成重庆吧',
        history: [
          { role: 'user', content: '成都 3 天' },
          { role: 'assistant', content: '好的，成都...' },
        ],
      },
      expected: {
        must_contain_pois: [{ name_contains: '解放碑', city: '重庆' }],
        must_not_contain_keywords: ['宽窄巷子', '锦里', '春熙路'],
      },
    })
    const out = makeOutput({
      text: '推荐重庆解放碑、洪崖洞。',
      json: { city: '重庆', dailyItinerary: [{ day: 1, morning: { spot: '解放碑步行街' } }] },
    })
    expect(destinationOverride(out, f).pass).toBe(true)
  })

  it('多轮改目的地 + Agent 没跟随还在讲成都 → fail', () => {
    const f = makeFixture({
      input: {
        message: '那改成重庆吧',
        history: [
          { role: 'user', content: '成都 3 天' },
          { role: 'assistant', content: '好的，成都...' },
        ],
      },
      expected: {
        must_contain_pois: [{ name_contains: '解放碑', city: '重庆' }],
        must_not_contain_keywords: ['宽窄巷子', '锦里', '春熙路'],
      },
    })
    const out = makeOutput({
      text: '成都宽窄巷子、锦里必去',
      json: { city: '成都', dailyItinerary: [{ day: 1, morning: { spot: '宽窄巷子' } }] },
    })
    const r = destinationOverride(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('宽窄巷子')
  })
})

/* ============================================================
 * contextMemory
 * ============================================================ */
describe('contextMemory', () => {
  it('无 history → pass（跳过）', () => {
    expect(contextMemory(makeOutput(), makeFixture()).pass).toBe(true)
  })

  it('多轮追问 + Agent 提到上文 POI → pass', () => {
    const f = makeFixture({
      input: {
        message: 'Day 2 西湖游船多少钱？',
        history: [
          { role: 'user', content: '杭州 2 天' },
          { role: 'assistant', content: 'Day 1: ..., Day 2: 西湖游船。' },
        ],
      },
      expected: { must_contain_keywords: ['西湖', '游船', '码头'] },
    })
    const out = makeOutput({ text: '西湖游船在花港码头，120元/人。' })
    expect(contextMemory(out, f).pass).toBe(true)
  })

  it('多轮追问 + Agent 答非所问 → fail', () => {
    const f = makeFixture({
      input: {
        message: 'Day 2 西湖游船多少钱？',
        history: [
          { role: 'user', content: '杭州 2 天' },
          { role: 'assistant', content: 'Day 2: 西湖游船。' },
        ],
      },
      expected: { must_contain_keywords: ['西湖', '游船', '码头'] },
    })
    const out = makeOutput({ text: '好的，给你推荐成都 3 天行程...' })
    const r = contextMemory(out, f)
    expect(r.pass).toBe(false)
  })
})

/* ============================================================
 * noForcedItinerary
 * ============================================================ */
describe('noForcedItinerary', () => {
  it('非反例 fixture → pass（跳过）', () => {
    const f = makeFixture({ expected: { days: 3 } })
    expect(noForcedItinerary(makeOutput(), f).pass).toBe(true)
  })

  it('反例 + Agent 礼貌拒绝（不输出行程）→ pass', () => {
    const f = makeFixture({ expected: { json_valid: false, is_recommendation: true } })
    const out = makeOutput({ text: '推荐这几个 6 月适合去的城市：青岛、桂林、丽江。' })
    expect(noForcedItinerary(out, f).pass).toBe(true)
  })

  it('反例 + Agent 硬塞 Day 1 行程 → fail', () => {
    const f = makeFixture({ expected: { json_valid: false, is_recommendation: true } })
    const out = makeOutput({ text: '推荐成都 Day 1：上午宽窄巷子，下午锦里。' })
    const r = noForcedItinerary(out, f)
    expect(r.pass).toBe(false)
    expect(r.reason).toContain('Day')
  })

  it('反例 + Agent 输出 JSON dailyItinerary 数组 → fail', () => {
    const f = makeFixture({ expected: { json_valid: false, is_recommendation: true } })
    const out = makeOutput({
      text: '推荐如下',
      json: { dailyItinerary: [{ day: 1, morning: { spot: 'A' } }] },
    })
    const r = noForcedItinerary(out, f)
    expect(r.pass).toBe(false)
  })
})
