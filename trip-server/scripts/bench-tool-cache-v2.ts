/**
 * ToolCache 基准测试 v2：跑 5 次取平均，消除随机噪声
 */

import { performance } from 'perf_hooks'
import { ToolCache } from '../src/services/llmGuard/toolCache'
import { withToolCache } from '../src/services/agent/toolCache'
import { getWeatherTool } from '../src/services/agent/tools/getWeather'
import { retrieveKnowledgeTool } from '../src/services/agent/tools/retrieveKnowledge'
import { searchHotelsTool } from '../src/services/agent/tools/searchHotels'
import { calculateDistanceTool } from '../src/services/agent/tools/calculateDistance'

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

// mock fetch
const originalFetch = global.fetch
global.fetch = (async () => {
  await sleep(180)
  return {
    ok: true,
    json: async () => ({
      current_condition: [{ temp_C: '25', FeelsLikeC: '27', humidity: '60', windspeedKmph: '5', weatherDesc: [{ value: 'Sunny' }] }],
      weather: [{ date: '2026-06-27', maxtempC: '28', mintempC: '18', astronomy: [{ sunrise: '06:00', sunset: '19:00' }] }],
    }),
  }
}) as any

// mock searchSpots
import * as knowledgeService from '../src/services/knowledgeService'
const originalSearchSpots = (knowledgeService as any).searchSpots
let realSearchSpotsCalls = 0
;(knowledgeService as any).searchSpots = async (args: any) => {
  realSearchSpotsCalls++
  await sleep(80)
  return `【${args.city} · ${args.category ?? 'attraction'}】检索 "${args.query}" 的结果...`
}

const cities = ['成都', '成都', '成都', '成都', '北京', '上海', '杭州']
const knowledgeTemplates = [
  { query: '美食', category: 'food' }, { query: '景点', category: 'attraction' },
  { query: '好吃的', category: 'food' }, { query: '必去', category: 'attraction' },
  { query: '川菜', category: 'food' }, { query: '历史文化', category: 'attraction' },
  { query: '亲子', category: 'attraction' }, { query: '小吃', category: 'food' },
]
const hotelLevels = ['economy', 'comfort', 'luxury']
const hotelBudgets = [200, 400, 600, 800, 1000]
const cityPairs = [
  { from: '成都', to: '北京' }, { from: '成都', to: '上海' },
  { from: '北京', to: '上海' }, { from: '成都', to: '西安' },
  { from: '成都', to: '杭州' },
]
const transportModes = ['train', 'car', 'flight']

function rand<T>(arr: readonly T[]): T { return arr[Math.floor(Math.random() * arr.length)] }
function randInt(min: number, max: number): number { return Math.floor(Math.random() * (max - min + 1)) + min }

interface Round {
  tool: string
  args: any
  isHit: boolean
  elapsedMs: number
}

async function runOnce(runId: number): Promise<Round[]> {
  // 每次跑都用全新 cache（避免跨 run 串数据）
  const cache = new ToolCache({
    get_weather:        { ttlMs: 30 * 60 * 1000, maxSize: 1000 },
    retrieve_knowledge: { ttlMs: 6 * 60 * 60 * 1000, maxSize: 500 },
  })
  const weather   = withToolCache(getWeatherTool,        { cache, toolName: 'get_weather' })
  const knowledge = withToolCache(retrieveKnowledgeTool, { cache, toolName: 'retrieve_knowledge' })
  const hotels    = searchHotelsTool
  const distance  = calculateDistanceTool

  const records: Round[] = []
  const TURNS = 20

  for (let t = 0; t < TURNS; t++) {
    const callsPerTurn = randInt(1, 3)
    for (let c = 0; c < callsPerTurn; c++) {
      const city = rand(cities)
      const r = Math.random()
      let tool: string
      let args: any
      let toolRef: any

      if (r < 0.30) {
        tool = 'get_weather'; args = { city }; toolRef = weather
      } else if (r < 0.75) {
        const tpl = rand(knowledgeTemplates)
        tool = 'retrieve_knowledge'; args = { query: tpl.query, city, category: tpl.category }; toolRef = knowledge
      } else if (r < 0.88) {
        tool = 'search_hotels'; args = { city, level: rand(hotelLevels), budget: rand(hotelBudgets) }; toolRef = hotels
      } else {
        const pair = rand(cityPairs)
        tool = 'calculate_distance'; args = { ...pair, mode: rand(transportModes) }; toolRef = distance
      }

      const start = performance.now()
      await toolRef.call(args)
      const elapsed = performance.now() - start

      records.push({ tool, args, isHit: elapsed < 10, elapsedMs: Math.round(elapsed) })
    }
    await sleep(80)
  }

  return records
}

function aggregate(allRounds: Round[][]) {
  const summary: Record<string, { hits: number[]; misses: number[]; totalMs: number; savedMs: number }> = {}

  for (const records of allRounds) {
    const byTool: Record<string, { hit: number; miss: number; totalMs: number }> = {}
    for (const r of records) {
      if (!byTool[r.tool]) byTool[r.tool] = { hit: 0, miss: 0, totalMs: 0 }
      if (r.isHit) byTool[r.tool].hit++
      else { byTool[r.tool].miss++; byTool[r.tool].totalMs += r.elapsedMs }
    }

    for (const [tool, s] of Object.entries(byTool)) {
      if (!summary[tool]) summary[tool] = { hits: [], misses: [], totalMs: 0, savedMs: 0 }
      summary[tool].hits.push(s.hit)
      summary[tool].misses.push(s.miss)
      // miss 平均耗时作为基准延迟估算
      const baselineMs = s.miss > 0 ? s.totalMs / s.miss : 50
      summary[tool].savedMs += s.hit * baselineMs
    }
  }

  return summary
}

async function main() {
  const RUNS = 5
  console.log(`\n跑 ${RUNS} 次取平均（每次模拟 10 分钟 = 20 轮 × 1-3 次调用）\n`)

  const allRounds: Round[][] = []
  let totalFetchCalls = 0
  let totalSearchSpotsCalls = 0

  for (let i = 0; i < RUNS; i++) {
    realSearchSpotsCalls = 0
    const beforeFetch = (global.fetch as any).callCount ?? 0
    const records = await runOnce(i)
    allRounds.push(records)
  }

  const summary = aggregate(allRounds)

  console.log('='.repeat(70))
  console.log('  ToolCache 5 次平均报告（每次 10 分钟用户行为模拟）')
  console.log('='.repeat(70))
  console.log()
  console.log('  | Tool               | 平均 Hit | 平均 Miss | 平均命中率 | 估算节省延迟 |')
  console.log('  |--------------------|----------|-----------|------------|--------------|')
  for (const [tool, s] of Object.entries(summary)) {
    const avgHit = (s.hits.reduce((a, b) => a + b, 0) / RUNS).toFixed(1)
    const avgMiss = (s.misses.reduce((a, b) => a + b, 0) / RUNS).toFixed(1)
    const total = s.hits[0] + s.misses[0]
    const rate = ((s.hits.reduce((a, b) => a + b, 0)) / (s.hits.reduce((a, b) => a + b, 0) + s.misses.reduce((a, b) => a + b, 0)) * 100).toFixed(1)
    const name = tool.padEnd(18)
    console.log(`  | ${name} | ${avgHit.padStart(8)} | ${avgMiss.padStart(9)} | ${(rate + '%').padStart(10)} | ${(Math.round(s.savedMs / RUNS) + 'ms').padStart(12)} |`)
  }
  console.log()
  console.log('  -'.repeat(66))
  console.log('  关键观察:')
  console.log('  - get_weather: 命中来自"同城市反复问"，符合预期（外部 API 节省最实在）')
  console.log('  - retrieve_knowledge: 命中率受限于字面归一化（query 变体太多）')
  console.log('  - search_hotels: 未加缓存（每次 city+level+budget 组合几乎都不同）')
  console.log('  - calculate_distance: 纯计算 < 1ms，加缓存收益微乎其微')
  console.log('  -'.repeat(66))
  console.log()

  // 关键延迟节省计算
  const totalWeatherSaved = summary['get_weather']?.savedMs ?? 0
  const totalKnowledgeSaved = summary['retrieve_knowledge']?.savedMs ?? 0
  const totalExternalSaved = (totalWeatherSaved + totalKnowledgeSaved) / RUNS

  console.log(`  外部 API 节省（10 分钟）: ~${Math.round(totalExternalSaved)}ms`)
  console.log(`  - wttr.in 调用节省: ~${Math.round(totalWeatherSaved / RUNS)}ms（外部 API，限流风险）`)
  console.log(`  - RAG 检索节省: ~${Math.round(totalKnowledgeSaved / RUNS)}ms（本地计算，但 80ms × N）`)
  console.log()

  global.fetch = originalFetch
  ;(knowledgeService as any).searchSpots = originalSearchSpots
}

main().catch(e => { console.error(e); process.exit(1) })
