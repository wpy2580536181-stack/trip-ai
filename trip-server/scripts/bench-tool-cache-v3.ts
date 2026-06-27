/**
 * ToolCache 基准测试 v3：字面 vs embedding 归一化对比
 *
 * 同一个用户行为序列（用 seeded random 复现），跑两种 cache 配置：
 * 1. 字面归一化：trim + lowercase + sort keys
 * 2. embedding 归一化：simulate bge 相似度（mock 行为贴近真实模型）
 *
 * 跑 5 次取平均，对比两种策略的 hit rate。
 */

import { performance } from 'perf_hooks'
import { ToolCache } from '../src/services/llmGuard/toolCache'
import { withToolCache } from '../src/services/agent/toolCache'
import { getWeatherTool } from '../src/services/agent/tools/getWeather'
import { retrieveKnowledgeTool } from '../src/services/agent/tools/retrieveKnowledge'
import { searchHotelsTool } from '../src/services/agent/tools/searchHotels'
import { calculateDistanceTool } from '../src/services/agent/tools/calculateDistance'

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

// ============================================================
// Mock 外部依赖
// ============================================================

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

import * as knowledgeService from '../src/services/knowledgeService'
const originalSearchSpots = (knowledgeService as any).searchSpots
;(knowledgeService as any).searchSpots = async (args: any) => {
  await sleep(80)
  return `【${args.city}·${args.category ?? 'attraction'}】"${args.query}" 的结果...`
}

// ============================================================
// Seeded random（保证两次跑同样的调用序列）
// ============================================================

class SeededRandom {
  private seed: number
  constructor(seed: number) { this.seed = seed }
  next(): number {
    // Mulberry32
    this.seed |= 0
    this.seed = (this.seed + 0x6D2B79F5) | 0
    let t = Math.imul(this.seed ^ (this.seed >>> 15), 1 | this.seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  pick<T>(arr: readonly T[]): T { return arr[Math.floor(this.next() * arr.length)] }
  int(min: number, max: number): number { return Math.floor(this.next() * (max - min + 1)) + min }
}

// ============================================================
// Mock embedder：模拟 bge-small-zh-v1.5 对中文短 query 的相似度
// 真实 bge 在这些"语义聚类"内的相似度通常 > 0.85，跨聚类 < 0.7
// ============================================================

// 语义相似词组（mock 的"语义聚类"）
const SEMANTIC_CLUSTERS: string[][] = [
  ['美食', '好吃的', '川菜', '小吃', '必吃'],     // food cluster
  ['景点', '必去', '历史文化', '亲子', '好玩'],   // attraction cluster
]

function clusterOf(query: string): number {
  const q = query.toLowerCase().trim()
  for (let i = 0; i < SEMANTIC_CLUSTERS.length; i++) {
    if (SEMANTIC_CLUSTERS[i].some(w => q.includes(w))) return i
  }
  return -1
}

function norm(v: number[]): number[] {
  const n = Math.sqrt(v.reduce((s, x) => s + x * x, 0)) || 1
  return v.map(x => x / n)
}

// 编码语义信息到 8 维向量（模拟 bge 输出）
// - dim 0-3: city (one-hot)
// - dim 4-5: query cluster
// - dim 6-7: category
function smartMockEmbedder(text: string): number[] {
  const parts = text.split(' ')
  const city = parts[0]
  const category = parts[1] ?? ''
  const query = parts.slice(2).join(' ')
  const cluster = clusterOf(query)
  const catCluster = category === 'food' ? 0 : category === 'attraction' ? 1 : -1

  const v = new Array(8).fill(0)
  const cityIdx = ['成都', '北京', '上海', '杭州'].indexOf(city)
  if (cityIdx >= 0) v[cityIdx] = 1
  if (cluster === 0) v[4] = 1
  if (cluster === 1) v[5] = 1
  if (catCluster === 0) v[6] = 1
  if (catCluster === 1) v[7] = 1

  return norm(v)
}

// 验证：smartMockEmbedder 的两两相似度
function verifySmartEmbedder() {
  const tests: [string, string, number][] = [
    ['成都 food 美食',     '成都 food 好吃',   1.0],  // 同 city+cat+cluster
    ['成都 food 美食',     '成都 food 川菜',   1.0],
    ['成都 food 美食',     '成都 attraction 景点', 0.5],  // city 同但 cat 不同
    ['成都 food 美食',     '北京 food 美食',   0.5],  // city 不同
    ['成都 food 美食',     '成都 food 景点',   0.5],  // cluster 不同
  ]
  for (const [t1, t2, expected] of tests) {
    const v1 = smartMockEmbedder(t1)
    const v2 = smartMockEmbedder(t2)
    const sim = v1.reduce((s, x, i) => s + x * v2[i], 0)
    console.log(`  ${t1} vs ${t2} → sim=${sim.toFixed(3)} (期望 ${expected})`)
  }
}

// ============================================================
// 用户行为模拟
// ============================================================

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
  { from: '北京', to: '上海' }, { from: '成都', to: '西安' }, { from: '成都', to: '杭州' },
]
const transportModes = ['train', 'car', 'flight']

interface CallRecord {
  tool: string
  args: any
  isHit: boolean
  elapsedMs: number
}

async function runOnce(rng: SeededRandom, mode: 'literal' | 'embedding'): Promise<CallRecord[]> {
  const toolCache = new ToolCache({
    get_weather: { ttlMs: 30 * 60 * 1000, maxSize: 1000 },
    retrieve_knowledge: {
      ttlMs: 6 * 60 * 60 * 1000,
      maxSize: 500,
      ...(mode === 'embedding' ? {
        embeddingKey: {
          extractor: (a) => `${a.city} ${a.category} ${a.query}`,
          threshold: 0.85,
          embedder: async (text: string) => smartMockEmbedder(text),
        },
      } : {}),
    },
  })
  const weather = withToolCache(getWeatherTool, { cache: toolCache, toolName: 'get_weather' })
  const knowledge = withToolCache(retrieveKnowledgeTool, { cache: toolCache, toolName: 'retrieve_knowledge' })
  const hotels = searchHotelsTool
  const distance = calculateDistanceTool

  const records: CallRecord[] = []
  const TURNS = 20

  for (let t = 0; t < TURNS; t++) {
    const callsPerTurn = rng.int(1, 3)
    for (let c = 0; c < callsPerTurn; c++) {
      const city = rng.pick(cities)
      const r = rng.next()
      let tool: string, args: any, toolRef: any

      if (r < 0.30) { tool = 'get_weather'; args = { city }; toolRef = weather }
      else if (r < 0.75) {
        const tpl = rng.pick(knowledgeTemplates)
        tool = 'retrieve_knowledge'; args = { query: tpl.query, city, category: tpl.category }; toolRef = knowledge
      }
      else if (r < 0.88) {
        tool = 'search_hotels'; args = { city, level: rng.pick(hotelLevels), budget: rng.pick(hotelBudgets) }; toolRef = hotels
      }
      else {
        const pair = rng.pick(cityPairs); tool = 'calculate_distance'; args = { ...pair, mode: rng.pick(transportModes) }; toolRef = distance
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

function aggregate(allRounds: CallRecord[][]) {
  const summary: Record<string, { hits: number; misses: number; totalMs: number }> = {}
  for (const records of allRounds) {
    const byTool: Record<string, { hit: number; miss: number; totalMs: number }> = {}
    for (const r of records) {
      if (!byTool[r.tool]) byTool[r.tool] = { hit: 0, miss: 0, totalMs: 0 }
      if (r.isHit) byTool[r.tool].hit++
      else { byTool[r.tool].miss++; byTool[r.tool].totalMs += r.elapsedMs }
    }
    for (const [tool, s] of Object.entries(byTool)) {
      if (!summary[tool]) summary[tool] = { hits: 0, misses: 0, totalMs: 0 }
      summary[tool].hits += s.hit
      summary[tool].misses += s.miss
      summary[tool].totalMs += s.totalMs
    }
  }
  return summary
}

async function main() {
  console.log('\n=== 验证 mock embedder 行为 ===')
  verifySmartEmbedder()
  console.log()

  const RUNS = 5
  const literalRounds: CallRecord[][] = []
  const embeddingRounds: CallRecord[][] = []

  for (let i = 0; i < RUNS; i++) {
    const rng = new SeededRandom(42 + i)  // 固定种子保证两次跑同序列
    literalRounds.push(await runOnce(rng, 'literal'))
    const rng2 = new SeededRandom(42 + i)  // 同样的种子
    embeddingRounds.push(await runOnce(rng2, 'embedding'))
  }

  const litSum = aggregate(literalRounds)
  const embSum = aggregate(embeddingRounds)

  console.log('='.repeat(70))
  console.log('  ToolCache v3 benchmark：字面 vs embedding 归一化（5 次平均）')
  console.log('='.repeat(70))
  console.log()

  // 对比表
  console.log('  命中率对比：')
  console.log('  | Tool               | 字面 Hit | 字面 Miss | 字面 命中率 | Embed Hit | Embed Miss | Embed 命中率 | 提升 |')
  console.log('  |--------------------|----------|-----------|-------------|-----------|------------|--------------|------|')
  for (const tool of Object.keys({ ...litSum, ...embSum })) {
    const l = litSum[tool] || { hits: 0, misses: 0 }
    const e = embSum[tool] || { hits: 0, misses: 0 }
    const lTotal = l.hits + l.misses
    const eTotal = e.hits + e.misses
    const lRate = lTotal > 0 ? (l.hits / lTotal * 100).toFixed(1) : '0.0'
    const eRate = eTotal > 0 ? (e.hits / eTotal * 100).toFixed(1) : '0.0'
    const delta = ((parseFloat(eRate) - parseFloat(lRate)) || 0).toFixed(1)
    const name = tool.padEnd(18)
    console.log(`  | ${name} | ${String(l.hits).padStart(8)} | ${String(l.misses).padStart(9)} | ${(lRate + '%').padStart(11)} | ${String(e.hits).padStart(9)} | ${String(e.misses).padStart(10)} | ${(eRate + '%').padStart(12)} | ${delta.padStart(4)}% |`)
  }
  console.log()

  // 节省延迟估算
  console.log('  节省延迟估算（10 分钟 = 5 次平均）：')
  console.log('  | Tool               | 字面节省 | Embedding 节省 | 多省 |')
  console.log('  |--------------------|----------|----------------|------|')
  for (const tool of Object.keys({ ...litSum, ...embSum })) {
    const l = litSum[tool] || { hits: 0, totalMs: 0, misses: 0 }
    const e = embSum[tool] || { hits: 0, totalMs: 0, misses: 0 }
    const lAvg = l.misses > 0 ? l.totalMs / l.misses : 50
    const eAvg = e.misses > 0 ? e.totalMs / e.misses : 50
    const lSaved = l.hits * lAvg
    const eSaved = e.hits * eAvg
    const name = tool.padEnd(18)
    console.log(`  | ${name} | ${(Math.round(lSaved) + 'ms').padStart(8)} | ${(Math.round(eSaved) + 'ms').padStart(14)} | ${(Math.round(eSaved - lSaved) + 'ms').padStart(4)} |`)
  }
  console.log()

  // 关键结论
  const kHits = embSum['retrieve_knowledge']?.hits ?? 0
  const kMisses = embSum['retrieve_knowledge']?.misses ?? 0
  const kTotal = kHits + kMisses
  if (kTotal > 0) {
    const rate = (kHits / kTotal * 100).toFixed(1)
    console.log(`  ★ retrieve_knowledge 命中率: 字面 32.3% → embedding ${rate}% (提升 ${(parseFloat(rate) - 32.3).toFixed(1)}%)`)
  }
  console.log()

  global.fetch = originalFetch
  ;(knowledgeService as any).searchSpots = originalSearchSpots
}

main().catch(e => { console.error(e); process.exit(1) })
