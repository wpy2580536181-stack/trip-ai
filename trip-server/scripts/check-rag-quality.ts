/**
 * RAG 检索质量对比：当前简化版 vs 模拟 LLM 改写版
 *
 * 用法: npx tsx scripts/check-rag-quality.ts
 */
import 'dotenv/config'
import { searchSpots } from '../src/services/knowledgeService'

interface TestCase {
  label: string
  query: string
  city: string
  category?: 'attraction' | 'food' | 'hotel'
  // 模拟 LLM 改写的"理想关键词"
  idealKeywords: string
}

const TESTS: TestCase[] = [
  {
    label: '意图提取：亲子',
    query: '带老人小孩去玩方便的地方',
    city: '成都',
    category: 'attraction',
    idealKeywords: '成都 亲子 儿童 公园 乐园 博物馆',
  },
  {
    label: '意图提取：避暑',
    query: '夏天避暑去哪里比较好',
    city: '重庆',
    category: 'attraction',
    idealKeywords: '重庆 避暑 凉爽 山 森林公园 夏季',
  },
  {
    label: '意图提取：便宜',
    query: '预算200以内住哪里',
    city: '北京',
    category: 'hotel',
    idealKeywords: '北京 经济型 住宿 便宜 平价 低价酒店',
  },
  {
    label: '模糊语义：夜景',
    query: '看夜景最好的地方',
    city: '广州',
    category: 'attraction',
    idealKeywords: '广州 夜景 观景台 广州塔 珠江 地标',
  },
  {
    label: '模糊语义：约会',
    query: '适合情侣约会的浪漫餐厅',
    city: '上海',
    category: 'food',
    idealKeywords: '上海 情侣 约会 浪漫 西餐 氛围',
  },
  {
    label: '精确：门票',
    query: '北京故宫博物院的开放时间',
    city: '北京',
    category: 'attraction',
    idealKeywords: '北京 故宫博物院 开放时间 门票',
  },
]

function compareSets(actual: string, idealKeywords: string): string {
  const actualLines = actual.split('\n---\n')
  const actualNames = actualLines.map(l => l.split('\n')[0]?.replace(/^\d+\.\s*/, '')?.trim() || '')

  return actualNames.map((name, i) => {
    const desc = actualLines[i]?.split('\n').slice(1).join(' ').slice(0, 60) || ''
    return `    ${i + 1}. ${name}\n       ${desc}...`
  }).join('\n')
}

async function main() {
  console.log('=== RAG 检索质量对比 ===\n')

  for (const t of TESTS) {
    console.log(`━━━ ${t.label} ━━━`)
    console.log(`  query: "${t.query}" (${t.city})\n`)

    // 当前简化版
    const startCurrent = Date.now()
    const currentResult = await searchSpots({
      query: t.query,
      city: t.city,
      category: t.category,
      limit: 3,
    })
    const currentTime = Date.now() - startCurrent

    // 模拟 LLM 改写版：直接用理想关键词搜（相当于 LLM 改写后的效果）
    const startIdeal = Date.now()
    const idealResult = await searchSpots({
      query: t.idealKeywords,
      city: t.city,
      category: t.category,
      limit: 3,
    })
    const idealTime = Date.now() - startIdeal

    console.log(`  当前简化版 (${currentTime}ms):`)
    console.log(compareSets(currentResult, t.idealKeywords))
    console.log(`\n  理想改写版 (${idealTime}ms):`)
    console.log(compareSets(idealResult, t.idealKeywords))

    // 判断 top-1 是否一致
    const currentTop1 = currentResult.split('\n---\n')[0]?.split('\n')[0] || ''
    const idealTop1 = idealResult.split('\n---\n')[0]?.split('\n')[0] || ''
    const match = currentTop1 === idealTop1 ? '✅' : '⚠️ top-1 不同'
    console.log(`  ${match}\n`)
  }
}

main().catch(e => { console.error(e); process.exit(1) })
