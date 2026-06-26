/**
 * 场景 4：缓存效果压测
 *
 * 跑 50 个相似问题（city 不同但 system prompt 一样）
 * 然后查 /api/stats/token-usage/logs 算缓存命中率
 *
 * 注意：/recommend 限流 5/min（trip.routes.ts:18）→ 50 请求需 13s 间隔
 *       server 端 recommendCache 是按 cacheKey 缓存响应，50 个不同 city
 *       不会命中，所以会真实打到 DeepSeek，从而能测 prompt cache
 *       tokenUsageLog 是内存，重启清空；通过 timestamp 过滤本次请求
 */

import { saveResult, getEnv } from './lib/result-store'
import { getAuthToken } from './lib/auth'
import { RECOMMEND_RATE_LIMIT_PER_MIN } from '../../src/routes/trip.routes'

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000'
// Source of truth: src/routes/trip.routes.ts:RECOMMEND_RATE_LIMIT_PER_MIN
// 60s / max = minimum interval, +1s safety margin
const REQUEST_INTERVAL_MS = Math.ceil(60_000 / RECOMMEND_RATE_LIMIT_PER_MIN) + 1_000

async function main() {
  console.log('[cache] 启动缓存效果压测...')
  console.log(`[cache] 预计耗时: ~${Math.ceil(50 * REQUEST_INTERVAL_MS / 60_000)} 分钟`)
  const token = await getAuthToken(BASE_URL)

  const cities = ['北京', '上海', '成都', '西安', '杭州', '广州', '深圳', '重庆', '厦门', '青岛',
                  '苏州', '南京', '武汉', '长沙', '天津', '哈尔滨', '大连', '三亚', '丽江', '拉萨',
                  '敦煌', '吐鲁番', '喀什', '西宁', '银川', '呼和浩特', '太原', '济南', '连云港',
                  '宁波', '温州', '福州', '泉州', '珠海', '汕头', '湛江', '北海', '桂林', '贵阳',
                  '昆明', '大理', '西双版纳', '香格里拉', '稻城', '九寨沟', '黄山', '千岛湖', '普陀山', '雁荡山']

  // 记录压测开始时间（用于过滤 logs）
  const startTimestamp = Date.now()
  console.log(`[cache] startTimestamp: ${startTimestamp}`)

  let successCount = 0
  let rateLimitedCount = 0
  for (let i = 0; i < cities.length; i++) {
    const city = cities[i]
    try {
      const res = await fetch(`${BASE_URL}/api/trip/recommend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ city, days: 2, budget: 3000 }),
      })
      if (res.ok) {
        successCount++
      } else if (res.status === 429) {
        rateLimitedCount++
        console.log(`\n[cache] ${city}: 429 限流，等 20s 重试`)
        await new Promise(r => setTimeout(r, 20_000))
        const retry = await fetch(`${BASE_URL}/api/trip/recommend`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ city, days: 2, budget: 3000 }),
        })
        if (retry.ok) successCount++
      } else {
        console.log(`\n[cache] ${city}: HTTP ${res.status}`)
      }
    } catch (e: any) {
      console.log(`\n[cache] ${city}: ${e.message}`)
    }
    process.stdout.write(`[${i + 1}/${cities.length}]${successCount}✓ `)
    if (i < cities.length - 1) {
      await new Promise(r => setTimeout(r, REQUEST_INTERVAL_MS))
    }
  }
  console.log(`\n[cache] 完成 ${successCount}/${cities.length} 个请求（${rateLimitedCount} 次 429）`)

  // 等几秒让 tokenUsageLog 异步写入
  await new Promise(r => setTimeout(r, 3_000))

  // 查 token usage logs（global scope，eval-test 是 admin）
  const statsRes = await fetch(`${BASE_URL}/api/stats/token-usage/logs?scope=global&limit=200`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const statsData = (await statsRes.json()) as { data: any[] }
  const logs = statsData.data || []

  // 过滤本次压测产生的 logs（timestamp > startTimestamp）
  const benchLogs = logs.filter((l: any) => l.timestamp >= startTimestamp)

  const total = benchLogs.reduce((sum, l: any) => sum + (l.tokens || 0), 0)
  const cached = benchLogs.reduce((sum, l: any) => sum + (l.cached || 0), 0)
  const hitRate = total > 0 ? cached / total : 0

  const summary = {
    scenario: 'cache',
    env: getEnv(),
    totalRequests: successCount,
    rateLimited: rateLimitedCount,
    totalLogEntries: benchLogs.length,
    totalTokens: total,
    cachedTokens: cached,
    cacheHitRate: hitRate,
    estimatedSavingsRMB: cached * 0.0001,  // DeepSeek cache 折扣估算 ¥0.0001/token
  }
  saveResult('cache-results', summary)
  console.log(`[cache] 命中率: ${(hitRate * 100).toFixed(1)}% (${cached}/${total} tokens)`)
  console.log(`[cache] 估算节省: ¥${summary.estimatedSavingsRMB.toFixed(4)}`)
}

main().catch((e) => { console.error(e); process.exit(1) })
