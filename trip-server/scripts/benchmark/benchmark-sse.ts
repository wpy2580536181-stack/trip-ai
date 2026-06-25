/**
 * 场景 2：SSE 流式 chat 压测
 *
 * 用 Node 并发 fetch 测 /api/trip/chat 流式
 * 测：并发数 vs 流完成时间 / chunk 数 / token 数
 */

import { saveResult, percentile, getEnv } from './lib/result-store'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000'

interface SseMetric {
  concurrency: number
  totalStreams: number
  successStreams: number
  streamDurationsMs: number[]  // 每个流的总耗时
  chunkCounts: number[]
  tokenCounts: { prompt: number; completion: number; total: number }[]
  errors: number
}

async function getToken(): Promise<string> {
  const res = await fetch(`${BASE_URL}/api/user/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'eval-test', password: 'EvalTest@2026' }),
  })
  const data = (await res.json()) as { data: { token: string } }
  return data.data.token
}

async function runSseStream(token: string, message: string): Promise<{
  durationMs: number; chunks: number; tokens: { prompt: number; completion: number; total: number }; error?: string
}> {
  const start = Date.now()
  const res = await fetch(`${BASE_URL}/api/trip/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) return { durationMs: Date.now() - start, chunks: 0, tokens: { prompt: 0, completion: 0, total: 0 }, error: `HTTP ${res.status}` }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let chunks = 0
  let tokens = { prompt: 0, completion: 0, total: 0 }
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // 完整事件以 \n\n 结束
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const event = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const dataLine = event.split('\n').find((l) => l.startsWith('data: '))
      if (!dataLine) continue
      try {
        const data = JSON.parse(dataLine.slice(6))
        if (data.type === 'chunk') chunks++
        if (data.type === 'complete' && data.data?.usage) tokens = data.data.usage
      } catch { /* ignore */ }
    }
  }
  return { durationMs: Date.now() - start, chunks, tokens }
}

async function runConcurrency(concurrency: number, totalStreams: number, token: string): Promise<SseMetric> {
  const messages = [
    '北京 2 天美食', '上海 1 天经典', '成都 3 天慢节奏', '西安 2 天文化',
    '杭州 1 天西湖', '广州 2 天美食', '深圳 1 天现代', '重庆 2 天夜景',
  ]
  const metrics: SseMetric = {
    concurrency, totalStreams, successStreams: 0,
    streamDurationsMs: [], chunkCounts: [], tokenCounts: [], errors: 0,
  }
  let idx = 0
  async function worker() {
    while (idx < totalStreams) {
      const myIdx = idx++
      if (myIdx >= totalStreams) break
      const msg = messages[myIdx % messages.length]
      try {
        const r = await runSseStream(token, msg)
        if (r.error) {
          metrics.errors++
        } else {
          metrics.successStreams++
          metrics.streamDurationsMs.push(r.durationMs)
          metrics.chunkCounts.push(r.chunks)
          metrics.tokenCounts.push(r.tokens)
        }
      } catch (e) {
        metrics.errors++
      }
    }
  }
  await Promise.all(Array.from({ length: concurrency }, () => worker()))
  return metrics
}

async function main() {
  console.log('[sse] 启动 SSE 流式压测...')
  const token = await getToken()

  const results: SseMetric[] = []
  for (const conc of [1, 5, 10, 20]) {
    console.log(`[sse] 并发数: ${conc}`)
    const m = await runConcurrency(conc, 20, token)
    results.push(m)
    console.log(`  完成 ${m.successStreams}/${m.totalStreams} 流，P50=${percentile(m.streamDurationsMs, 50)}ms P99=${percentile(m.streamDurationsMs, 99)}ms`)
  }

  saveResult('sse-results', { scenario: 'sse', env: getEnv(), results })
  console.log('[sse] 完成')
}

main().catch((e) => { console.error(e); process.exit(1) })
