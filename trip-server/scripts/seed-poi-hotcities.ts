/**
 * 热门城市 POI 增量导入 — 每个城市 ~100 条
 *
 * 用法: npx tsx scripts/seed-poi-hotcities.ts
 *
 * 用多组关键词搜每类 POI，与 DB 已有数据去重后导入
 */
import 'dotenv/config'
import * as amapMcpProcess from '../src/services/mcp/amapMcpProcess'
import * as amapMcpClient from '../src/services/mcp/amapMcpClient'
import { bulkImportSpots } from '../src/services/knowledgeService'
import type { SpotInput } from '../src/types/agent'
import prisma from '../src/config/database'

// 热门旅游城市（按热度排序）
const CITIES: string[] = [
  '北京', '上海', '广州', '深圳', '重庆', '杭州', '武汉', '三亚',
  '西安', '长沙', '苏州', '天津', '宁波', '南昌', '昆明', '桂林',
  '成都', '南京', '厦门', '青岛', '大连', '丽江', '大理', '黄山',
  '张家界', '敦煌', '拉萨', '哈尔滨', '西双版纳',
]

// 每类用多个关键词覆盖不同 POI
const CATEGORY_KEYWORDS: Record<string, string[]> = {
  attraction: ['景点', '公园', '博物馆', '古迹', '风景区', '古镇'],
  food: ['美食', '小吃', '火锅', '餐厅', '特色菜', '夜市'],
  hotel: ['酒店', '民宿', '度假村', '商务酒店', '客栈'],
}

const CACHE_DURATION_MS = 30 * 24 * 60 * 60 * 1000 // for unsplash cache

/** 从 MCP 响应中解析 POI 列表 */
function parsePois(raw: string, city: string, category: SpotInput['category']): SpotInput[] {
  try {
    const data = JSON.parse(raw)
    const pois = data?.pois || []
    return pois.map((poi: any) => ({
      name: (poi.name || '').slice(0, 100),
      city,
      category,
      description: (poi.address ? `位于${poi.address}` : poi.name || '').slice(0, 500),
      tags: poi.typecode ? [poi.typecode.slice(0, 6)] : [],
    }))
  } catch {
    return []
  }
}

async function main() {
  console.log(`\n=== 热门城市 POI 增量导入 ===`)

  // 1. 加载已有数据（用于去重）
  console.log('\n[1/5] 加载已有数据...')
  const existing = await prisma.spot.findMany({ select: { city: true, name: true, category: true } })
  const existingSet = new Set(existing.map(s => `${s.city}:${s.name}:${s.category}`))
  console.log(`  DB 中已有 ${existing.length} 条`)

  // 2. 启动 MCP
  console.log('\n[2/5] 启动 Amap MCP...')
  await amapMcpProcess.start()
  if (!amapMcpProcess.isAlive()) { console.error('MCP 启动失败'); process.exit(1) }
  await amapMcpClient.connect()
  console.log('  MCP 就绪')

  // 3. 搜索 + 去重 + 导入
  console.log('\n[3/5] 搜索 POI...')
  let totalNew = 0
  let totalSkipped = 0

  for (let ci = 0; ci < CITIES.length; ci++) {
    const city = CITIES[ci]
    const citySpots: SpotInput[] = []
    const seen = new Set<string>()

    for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
      for (const kw of keywords) {
        try {
          const raw = await amapMcpClient.callTool('maps_text_search', { keywords: `${kw}`, city })
          const parsed = parsePois(raw, city, category as SpotInput['category'])
          for (const spot of parsed) {
            const key = `${spot.city}:${spot.name}:${spot.category}`
            if (seen.has(key) || existingSet.has(key)) continue
            seen.add(key)
            citySpots.push(spot)
          }
        } catch (err) {
          // ignore individual failures
        }
        await new Promise(r => setTimeout(r, 100))
      }
    }

    console.log(`  [${ci + 1}/${CITIES.length}] ${city}: 搜到 ${citySpots.length} 条新数据`)
    if (citySpots.length === 0) { totalSkipped++; continue }

    const result = await bulkImportSpots(citySpots)
    totalNew += result.success
    totalSkipped += result.failed
  }

  // 4. 清理
  console.log('\n[4/5] 关闭 MCP...')
  amapMcpClient.close()
  amapMcpProcess.stop()

  // 5. 最终统计
  console.log('\n[5/5] 结果')
  const finalCount = await prisma.spot.count()
  console.log(`  导入新数据: ${totalNew}`)
  console.log(`  DB 总数: ${finalCount}`)
  console.log('\n=== 完成 ===')
  await prisma.$disconnect()
  process.exit(0)
}

main().catch(err => {
  console.error('脚本失败:', err)
  amapMcpClient.close()
  amapMcpProcess.stop()
  process.exit(1)
})
