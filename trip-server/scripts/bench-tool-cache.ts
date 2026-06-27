/**
 * ToolCache 基准测试（10 分钟用户行为模拟）
 *
 * 模拟场景：
 * - 20 轮用户消息（每轮 30 秒，模拟 10 分钟对话）
 * - 每轮 1-3 次 tool 调用，共 ~50 次
 * - city 偏"成都"（67%），其他 3 个城市分散
 * - 同 query 高重复（模拟用户反复确认）
 *
 * 工具调用分布（贴近真实）：
 * - 30% 天气（同城市反复问"今天/明天/后天"）
 * - 45% 知识库（景点/美食检索，字面多变但语义同）
 * - 13% 酒店（city+level+budget 组合）
 * - 12% 距离（city 对 + 交通方式）
 *
 * 输出：各 tool 的 hit/miss/命中率/节省延迟
 */

import { performance } from 'perf_hooks'

// ============================================================
// 1. 准备外部依赖的 mock
// ============================================================

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

let fetchCallCount = 0
const originalFetch = global.fetch
global.fetch = (async (_url: any, _opts?: any) => {
  fetchCallCount++
  await sleep(180)  // 模拟 wttr.in 网络延迟
  return {
    ok: true,
    json: async () => ({
      current_condition: [{
        temp_C: '25', FeelsLikeC: '27', humidity: '60', windspeedKmph: '5',
        weatherDesc: [{ value: 'Sunny' }],
      }],
      weather: [
        { date: '2026-06-27', maxtempC: '28', mintempC: '18', astronomy: [{ sunrise: '06:00', sunset: '19:00' }] },
        { date: '2026-06-28', maxtempC: '30', mintempC: '20', astronomy: [{ sunrise: '06:01', sunset: '19:01' }] },
        { date: '2026-06-29', maxtempC: '27', mintempC: '19', astronomy: [{ sunrise: '06:02', sunset: '19:02' }] },
      ],
    }),
  }
}) as any

// mock knowledgeService.searchSpots
import * as knowledgeService from '../src/services/knowledgeService'
const originalSearchSpots = (knowledgeService as any).searchSpots
;(knowledgeService as any).searchSpots = async (args: any) => {
  await sleep(80)  // 模拟 RAG 检索延迟
  const cat = args.category ?? 'attraction'
  return `【${args.city} · ${cat}】检索 "${args.query}"：\n` +
    `1. 宽窄巷子 - 老成都生活场景 (4.5分) ¥0\n` +
    `2. 锦里古街 - 三国民俗商业街 (4.6分) ¥0\n` +
    `3. 武侯祠 - 三国文化圣地 (4.7分) ¥50\n` +
    `4. 大熊猫繁育研究基地 - 萌宠近距离 (4.8分) ¥55\n` +
    `5. 春熙路太古里 - 时尚商圈 (4.4分) ¥0`
}

// ============================================================
// 2. 构造真实的 tool 链路（withToolCache → withResilience → 真实 tool）
// ============================================================

import { ToolCache } from '../src/services/llmGuard/toolCache'
import { withToolCache } from '../src/services/agent/toolCache'
import { getWeatherTool } from '../src/services/agent/tools/getWeather'
import { retrieveKnowledgeTool } from '../src/services/agent/tools/retrieveKnowledge'
import { searchHotelsTool } from '../src/services/agent/tools/searchHotels'
import { calculateDistanceTool } from '../src/services/agent/tools/calculateDistance'

const cache = new ToolCache({
  get_weather:        { ttlMs: 30 * 60 * 1000, maxSize: 1000 },
  retrieve_knowledge: { ttlMs: 6 * 60 * 60 * 1000, maxSize: 500 },
})

const weather   = withToolCache(getWeatherTool,        { cache, toolName: 'get_weather' })
const knowledge = withToolCache(retrieveKnowledgeTool, { cache, toolName: 'retrieve_knowledge' })
const hotels    = searchHotelsTool
const distance  = calculateDistanceTool

// ============================================================
// 3. 用户行为模拟
// ============================================================

const cities = ['成都', '成都', '成都', '成都', '北京', '上海', '杭州']
const CITIES = ['成都', '北京', '上海', '杭州']  // 列出方便调试

const knowledgeTemplates = [
  { query: '美食',       category: 'food' },
  { query: '景点',       category: 'attraction' },
  { query: '好吃的',     category: 'food' },
  { query: '必去',       category: 'attraction' },
  { query: '川菜',       category: 'food' },
  { query: '历史文化',   category: 'attraction' },
  { query: '亲子',       category: 'attraction' },
  { query: '小吃',       category: 'food' },
]
const hotelLevels = ['economy', 'comfort', 'luxury']
const hotelBudgets = [200, 400, 600, 800, 1000]
const cityPairs = [
  { from: '成都', to: '北京' },
  { from: '成都', to: '上海' },
  { from: '北京', to: '上海' },
  { from: '成都', to: '西安' },
  { from: '成都', to: '杭州' },
]
const transportModes = ['train', 'car', 'flight']

function rand<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}
function randInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

interface CallRecord {
  tool: string
  args: Record<string, any>
  elapsedMs: number
  isHit: boolean
  resultPreview: string
}

async function simulate10min(): Promise<CallRecord[]> {
  const records: CallRecord[] = []
  const TURNS = 20
  const HIT_THRESHOLD_MS = 10  // < 10ms 视为 hit（in-memory lookup 极快）

  for (let t = 0; t < TURNS; t++) {
    const callsPerTurn = randInt(1, 3)
    for (let c = 0; c < callsPerTurn; c++) {
      const city = rand(cities)
      const r = Math.random()
      let tool: string
      let args: Record<string, any>
      let toolRef: any

      if (r < 0.30) {
        // 30% 天气
        tool = 'get_weather'
        args = { city }
        toolRef = weather
      } else if (r < 0.75) {
        // 45% 知识库
        const tpl = rand(knowledgeTemplates)
        tool = 'retrieve_knowledge'
        args = { query: tpl.query, city, category: tpl.category }
        toolRef = knowledge
      } else if (r < 0.88) {
        // 13% 酒店
        tool = 'search_hotels'
        args = { city, level: rand(hotelLevels), budget: rand(hotelBudgets) }
        toolRef = hotels
      } else {
        // 12% 距离
        const pair = rand(cityPairs)
        tool = 'calculate_distance'
        args = { ...pair, mode: rand(transportModes) }
        toolRef = distance
      }

      const start = performance.now()
      const result = await toolRef.call(args) as string
      const elapsed = performance.now() - start

      records.push({
        tool,
        args,
        elapsedMs: Math.round(elapsed),
        isHit: elapsed < HIT_THRESHOLD_MS,
        resultPreview: result.slice(0, 40).replace(/\n/g, ' '),
      })
    }

    // 模拟用户思考时间（压缩到 80ms 一轮）
    await sleep(80)
  }

  return records
}

// ============================================================
// 4. 输出报告
// ============================================================

function printReport(records: CallRecord[], wallClockMs: number) {
  const byTool: Record<string, { hit: number; miss: number; totalMs: number }> = {}
  for (const r of records) {
    if (!byTool[r.tool]) byTool[r.tool] = { hit: 0, miss: 0, totalMs: 0 }
    const s = byTool[r.tool]
    if (r.isHit) s.hit++
    else { s.miss++; s.totalMs += r.elapsedMs }
  }

  // 估算未走 cache 时的延迟（用 miss 的平均时间作为"如果不加 cache"）
  const baselineByTool: Record<string, number> = {}
  for (const [tool, s] of Object.entries(byTool)) {
    baselineByTool[tool] = s.miss > 0 ? s.totalMs / s.miss : 50
  }
  const totalSavedMs = records.reduce((sum, r) => {
    if (r.isHit) return sum + (baselineByTool[r.tool] ?? 100)
    return sum
  }, 0)

  console.log('='.repeat(64))
  console.log('  ToolCache 基准测试报告（10 分钟用户行为模拟）')
  console.log('='.repeat(64))
  console.log()
  console.log(`  总调用次数:        ${records.length}`)
  console.log(`  实际跑时间:        ${wallClockMs}ms（压缩）`)
  console.log(`  缓存配置:`)
  console.log(`    get_weather:        TTL 30 min,  maxSize 1000`)
  console.log(`    retrieve_knowledge: TTL  6 h,    maxSize 500`)
  console.log(`    search_hotels / calculate_distance: 不加缓存`)
  console.log()
  console.log('-'.repeat(64))
  console.log('  各 Tool 命中率统计')
  console.log('-'.repeat(64))
  console.log()
  console.log('  | Tool               | Hit  | Miss | 命中率  | 平均 Miss 耗时 |')
  console.log('  |--------------------|------|------|---------|----------------|')
  for (const [tool, s] of Object.entries(byTool)) {
    const total = s.hit + s.miss
    const rate = total > 0 ? (s.hit / total * 100).toFixed(1) : '0.0'
    const avgMiss = s.miss > 0 ? `${Math.round(s.totalMs / s.miss)}ms` : '-'
    const name = tool.padEnd(18)
    console.log(`  | ${name} | ${String(s.hit).padStart(4)} | ${String(s.miss).padStart(4)} | ${rate.padStart(6)}% | ${avgMiss.padStart(14)} |`)
  }
  console.log()
  console.log(`  估算节省延迟:       ~${Math.round(totalSavedMs)}ms`)
  console.log(`  估算节省比例:       ${(totalSavedMs / (totalSavedMs + records.reduce((s, r) => s + r.elapsedMs, 0)) * 100).toFixed(1)}%`)
  console.log()
  console.log('-'.repeat(64))
  console.log('  外部 API 实际调用次数（应等于 miss 数）')
  console.log('-'.repeat(64))
  console.log()
  console.log(`  fetch (wttr.in):           ${fetchCallCount} 次`)
  console.log(`  searchSpots (knowledge):    ${(knowledgeService as any).searchSpots.mock ? '-' : 'N/A（mock 函数无 counter）'} 次`)
  console.log()
  console.log('-'.repeat(64))
  console.log('  详细调用流水（前 25 条）')
  console.log('-'.repeat(64))
  console.log()
  console.log('  | #  | Tool               | Args                              | 耗时  | 状态 |')
  console.log('  |----|--------------------|-----------------------------------|-------|------|')
  records.slice(0, 25).forEach((r, i) => {
    const num = String(i + 1).padStart(3)
    const toolName = r.tool.padEnd(18)
    const argsStr = JSON.stringify(r.args).slice(0, 33).padEnd(33)
    const ms = `${r.elapsedMs}ms`.padStart(5)
    const status = r.isHit ? '✓ hit ' : '✗ miss'
    console.log(`  | ${num} | ${toolName} | ${argsStr} | ${ms} | ${status} |`)
  })
  if (records.length > 25) {
    console.log(`  | ... | (省略 ${records.length - 25} 条)                                |       |      |`)
  }
  console.log()
  console.log('='.repeat(64))
}

async function main() {
  console.log('\n开始模拟...\n')
  const t0 = Date.now()
  const records = await simulate10min()
  const wallClockMs = Date.now() - t0

  printReport(records, wallClockMs)

  // 恢复
  global.fetch = originalFetch
  ;(knowledgeService as any).searchSpots = originalSearchSpots
}

main().catch(e => { console.error(e); process.exit(1) })
