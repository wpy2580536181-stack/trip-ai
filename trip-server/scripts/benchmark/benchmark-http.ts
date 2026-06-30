/**
 * 场景 1：普通 HTTP 压测
 *
 * 用 autocannon 测登录 / 查历史 接口
 * 输出 QPS / P50 / P95 / P99 / 错误率
 */

// @ts-ignore — autocannon 没有官方 .d.ts，用 require interop
import autocannon from 'autocannon'
import { saveResult, getEnv } from './lib/result-store'
import { getAuthToken, getEvalCredentials } from './lib/auth'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000'
const DURATION = 30  // seconds

async function main() {
  console.log('[http] 启动普通 HTTP 压测...')

  // 0) 先拿 token（避免 autocannon 登录压测触发限流后取不到 token）
  const token = await getAuthToken(BASE_URL)
  console.log(`[http] 拿到 token，长度=${token.length}`)

  // 1) 登录接口压测
  const loginResult = await autocannon({
    url: `${BASE_URL}/api/user/login`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(getEvalCredentials()),
    connections: 10,
    duration: DURATION,
  })

  // 3) 查历史接口
  const historyResult = await autocannon({
    url: `${BASE_URL}/api/history/trips`,
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
    connections: 10,
    duration: DURATION,
  })

  // 合并结果
  const loginSuccess = loginResult.requests.total - loginResult.non2xx - loginResult.errors
  const historySuccess = historyResult.requests.total - historyResult.non2xx - historyResult.errors

  const result = {
    scenario: 'http',
    env: getEnv(),
    config: {
      connections: 10,
      durationSec: DURATION,
      rateLimit: '20 req/min per (IP for login / userId for authed)',
    },
    login: {
      url: `${BASE_URL}/api/user/login`,
      qps: loginResult.requests.average,
      effectiveQps: +(loginSuccess / DURATION).toFixed(3),
      p50: loginResult.latency.p50,
      p95: loginResult.latency.p97_5,
      p99: loginResult.latency.p99,
      max: loginResult.latency.max,
      totalRequests: loginResult.requests.total,
      success2xx: loginSuccess,
      errors: loginResult.errors,
      non2xx: loginResult.non2xx,
      successRate: +(loginSuccess / loginResult.requests.total).toFixed(6),
    },
    history: {
      url: `${BASE_URL}/api/history/trips`,
      qps: historyResult.requests.average,
      effectiveQps: +(historySuccess / DURATION).toFixed(3),
      p50: historyResult.latency.p50,
      p95: historyResult.latency.p97_5,
      p99: historyResult.latency.p99,
      max: historyResult.latency.max,
      totalRequests: historyResult.requests.total,
      success2xx: historySuccess,
      errors: historyResult.errors,
      non2xx: historyResult.non2xx,
      successRate: +(historySuccess / historyResult.requests.total).toFixed(6),
    },
    notes: [
      '10 connections × 30s 触发服务端 rate limit（max=20/min/user）',
      'qps = autocannon 报告的请求率（包含被 429 拒的）',
      'effectiveQps = 2xx / duration，是接口真实吞吐',
      'p50/p95/p99 在被 429 大量污染时意义有限（max 来自少量成功样本）',
    ].join('; '),
  }
  saveResult('http-results', result)
  console.log('[http] 完成')
  console.log(`  登录 raw QPS: ${result.login.qps.toFixed(1)}, effectiveQps: ${result.login.effectiveQps}, P99: ${result.login.p99}ms, 2xx: ${result.login.success2xx}/${result.login.totalRequests}`)
  console.log(`  历史 raw QPS: ${result.history.qps.toFixed(1)}, effectiveQps: ${result.history.effectiveQps}, P99: ${result.history.p99}ms, 2xx: ${result.history.success2xx}/${result.history.totalRequests}`)
}

main().catch((e) => { console.error(e); process.exit(1) })
