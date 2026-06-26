/**
 * 场景 3：LLM 路由压测
 *
 * /api/trip/recommend 是最重的同步接口
 * 跑 10 次，记耗时
 */

import { saveResult, percentile, getEnv } from './lib/result-store'
import { getAuthToken } from './lib/auth'
import { RECOMMEND_RATE_LIMIT_PER_MIN } from '../../src/routes/trip.routes'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000'

interface LlmMetric {
  city: string
  days: number
  budget: number
  durationMs: number
  success: boolean
  error?: string
}

async function runRecommend(token: string, city: string, days: number, budget: number): Promise<LlmMetric> {
  const start = Date.now()
  try {
    const res = await fetch(`${BASE_URL}/api/trip/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ city, days, budget }),
    })
    const data = await res.json() as any
    if (!res.ok || !data.success) {
      return { city, days, budget, durationMs: Date.now() - start, success: false, error: data.error || `HTTP ${res.status}` }
    }
    return {
      city, days, budget,
      durationMs: Date.now() - start,
      success: true,
    }
  } catch (e: any) {
    return { city, days, budget, durationMs: Date.now() - start, success: false, error: e.message }
  }
}

async function main() {
  console.log('[llm] 启动 LLM 路由压测...')
  const token = await getAuthToken(BASE_URL)

  const queries = [
    { city: '北京', days: 2, budget: 3000 },
    { city: '北京', days: 3, budget: 5000 },
    { city: '上海', days: 2, budget: 3000 },
    { city: '上海', days: 3, budget: 5000 },
    { city: '成都', days: 3, budget: 3000 },
    { city: '西安', days: 2, budget: 3000 },
    { city: '杭州', days: 2, budget: 3000 },
    { city: '广州', days: 3, budget: 5000 },
    { city: '深圳', days: 2, budget: 3000 },
    { city: '重庆', days: 3, budget: 5000 },
  ]

  const INTER_CALL_DELAY_MS = Math.ceil(60_000 / RECOMMEND_RATE_LIMIT_PER_MIN) + 1_000  // /recommend rate limit (src/routes/trip.routes.ts) + 1s safety margin
  const results: LlmMetric[] = []
  for (let i = 0; i < queries.length; i++) {
    const q = queries[i]
    if (i > 0) await new Promise(r => setTimeout(r, INTER_CALL_DELAY_MS))
    process.stdout.write(`  ${q.city} ${q.days}天... `)
    const m = await runRecommend(token, q.city, q.days, q.budget)
    results.push(m)
    console.log(`${m.success ? '✓' : '✗'} ${m.durationMs}ms${m.error ? ' (' + m.error + ')' : ''}`)
  }

  const successMetrics = results.filter(r => r.success)
  const summary = {
    scenario: 'llm',
    env: getEnv(),
    totalRequests: results.length,
    successCount: successMetrics.length,
    durationP50: percentile(successMetrics.map(r => r.durationMs), 50),
    durationP95: percentile(successMetrics.map(r => r.durationMs), 95),
    durationP99: percentile(successMetrics.map(r => r.durationMs), 99),
    durationMax: successMetrics.length > 0 ? Math.max(...successMetrics.map(r => r.durationMs)) : 0,
    results,
  }
  saveResult('llm-results', summary)
  console.log(`[llm] 完成 — ${successMetrics.length}/${results.length} 成功`)
  if (successMetrics.length > 0) {
    console.log(`  P50: ${summary.durationP50}ms P99: ${summary.durationP99}ms`)
  }
}

main().catch((e) => { console.error(e); process.exit(1) })
