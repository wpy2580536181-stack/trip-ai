/**
 * RAG 检索速度压测
 * 用法: npx tsx scripts/benchmark-rag.ts
 */
import 'dotenv/config'
import { searchSpots } from '../src/services/knowledgeService'

const QUERIES = [
  // 热门景点
  { query: '北京故宫博物院的开放时间', city: '北京', category: 'attraction' },
  { query: '上海外滩附近有什么好玩的', city: '上海', category: 'attraction' },
  { query: '成都最适合晚上去的景点', city: '成都', category: 'attraction' },
  { query: '西安兵马俑门票多少钱', city: '西安', category: 'attraction' },
  { query: '杭州西湖边上的餐厅推荐', city: '杭州', category: 'food' },
  // 长尾查询
  { query: '桂林阳朔西街住宿', city: '桂林', category: 'hotel' },
  { query: '丽江古城到玉龙雪山怎么走', city: '丽江', category: 'attraction' },
  { query: '拉萨适合高反人群的景点', city: '拉萨', category: 'attraction' },
  { query: '三亚海鲜便宜的地方', city: '三亚', category: 'food' },
  { query: '张家界国家森林公园游玩路线', city: '张家界', category: 'attraction' },
  // 模糊语义查询
  { query: '带老人小孩去哪个城市方便', city: '成都', category: 'attraction' },
  { query: '夏天避暑去哪里比较好', city: '重庆', category: 'attraction' },
  { query: '适合情侣约会的浪漫餐厅', city: '上海', category: 'food' },
  { query: '预算200以内住哪里', city: '北京', category: 'hotel' },
  { query: '看夜景最好的地方', city: '广州', category: 'attraction' },
]

async function main() {
  console.log('=== RAG 检索速度压测 ===\n')
  console.log(`查询数: ${QUERIES.length}\n`)

  // 预热
  console.log('预热中...')
  await searchSpots({ query: '北京', city: '北京', category: 'attraction' })
  console.log('预热完成\n')

  const times: number[] = []

  for (let i = 0; i < QUERIES.length; i++) {
    const { query, city, category } = QUERIES[i]
    const start = Date.now()
    try {
      const result = await searchSpots({ query, city, category })
      const elapsed = Date.now() - start
      times.push(elapsed)
      const itemCount = result ? result.split('\n---\n').length : 0
      console.log(`  [${i + 1}] ${elapsed}ms | ${itemCount} 项 | ${query.slice(0, 20)}`)
    } catch (e) {
      console.log(`  [${i + 1}] FAIL | ${query.slice(0, 20)} | ${(e as Error).message}`)
    }
  }

  // 统计
  const sorted = [...times].sort((a, b) => a - b)
  const avg = Math.round(times.reduce((a, b) => a + b, 0) / times.length)
  const min = sorted[0]
  const max = sorted[sorted.length - 1]
  const p50 = sorted[Math.floor(sorted.length * 0.5)]
  const p95 = sorted[Math.floor(sorted.length * 0.95)]
  const p99 = sorted[Math.floor(sorted.length * 0.99)]

  console.log('\n=== 结果 ===')
  console.log(`  平均: ${avg}ms`)
  console.log(`  最小: ${min}ms`)
  console.log(`  最大: ${max}ms`)
  console.log(`  P50:  ${p50}ms`)
  console.log(`  P95:  ${p95}ms`)
  console.log(`  P99:  ${p99}ms`)
}

main().catch(e => { console.error(e); process.exit(1) })
