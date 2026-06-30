/**
 * 通过 Amap MCP maps_text_search 批量拉取 POI 数据并导入知识库
 *
 * 用法: npx ts-node scripts/seed-poi-mcp.ts
 *
 * 每城市搜景点/美食/酒店三类，结果自动去重后写入 MySQL + Chroma
 */
import 'dotenv/config'
import * as amapMcpProcess from '../src/services/mcp/amapMcpProcess'
import * as amapMcpClient from '../src/services/mcp/amapMcpClient'
import { bulkImportSpots } from '../src/services/knowledgeService'
import type { SpotInput } from '../src/types/agent'

const CITIES = [
  '北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', '南京', '重庆',
  '天津', '苏州', '长沙', '郑州', '东莞', '青岛', '沈阳', '宁波', '昆明', '大连',
  '厦门', '合肥', '佛山', '福州', '哈尔滨', '济南', '温州', '长春', '石家庄', '常州',
  '泉州', '南宁', '贵阳', '南昌', '太原', '烟台', '嘉兴', '南通', '金华', '珠海',
  '惠州', '徐州', '海口', '乌鲁木齐', '绍兴', '中山', '台州', '兰州', '潍坊', '保定',
  '镇江', '扬州', '桂林', '唐山', '三亚', '湖州', '呼和浩特', '廊坊', '洛阳', '威海',
  '盐城', '临沂', '江门', '汕头', '泰州', '漳州', '邯郸', '芜湖', '银川', '淄博',
  '襄阳', '柳州', '赣州', '西宁',
]

const CATEGORIES: Array<{ keyword: string; category: SpotInput['category'] }> = [
  { keyword: '景点', category: 'attraction' },
  { keyword: '美食', category: 'food' },
  { keyword: '酒店', category: 'hotel' },
]

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

// 去重：跳过已有 name+city 的记录
const seen = new Set<string>()
function isDuplicate(spot: SpotInput): boolean {
  const key = `${spot.city}:${spot.name}:${spot.category}`
  if (seen.has(key)) return true
  seen.add(key)
  return false
}

async function main() {
  console.log(`\n=== Amap MCP POI 批量导入 ===`)
  console.log(`目标: ${CITIES.length} 城市 × 3 类 = ${CITIES.length * 3} 次搜索`)

  // 启动 MCP
  console.log('\n[1/4] 启动 Amap MCP...')
  await amapMcpProcess.start()
  if (!amapMcpProcess.isAlive()) {
    console.error('MCP 进程启动失败')
    process.exit(1)
  }
  await amapMcpClient.connect()
  console.log('MCP 就绪')

  // 搜索并导入
  console.log('\n[2/4] 搜索 POI...')
  let totalImported = 0
  let totalFailed = 0

  for (let i = 0; i < CITIES.length; i++) {
    const city = CITIES[i]
    const spots: SpotInput[] = []

    for (const { keyword, category } of CATEGORIES) {
      try {
        const raw = await amapMcpClient.callTool('maps_text_search', { keywords: keyword, city })
        const parsed = parsePois(raw, city, category)
        spots.push(...parsed)
      } catch (err) {
        console.error(`  ${city}/${keyword} 搜索失败:`, (err as Error)?.message?.slice(0, 80))
      }
    }

    // 去重
    const unique = spots.filter(s => !isDuplicate(s))
    if (unique.length === 0) {
      console.log(`  [${i + 1}/${CITIES.length}] ${city}: 无新数据`)
      continue
    }

    console.log(`  [${i + 1}/${CITIES.length}] ${city}: ${spots.length} 条 (去重后 ${unique.length} 条)`)
    const result = await bulkImportSpots(unique)
    totalImported += result.success
    totalFailed += result.failed

    // 小延迟防限流
    await new Promise(r => setTimeout(r, 200))
  }

  // 清理
  console.log('\n[3/4] 关闭 MCP...')
  amapMcpClient.close()
  amapMcpProcess.stop()

  console.log('\n[4/4] 结果')
  console.log(`  城市: ${CITIES.length}`)
  console.log(`  导入: ${totalImported}`)
  console.log(`  失败: ${totalFailed}`)
  console.log('\n=== 完成 ===')
  process.exit(0)
}

main().catch(err => {
  console.error('脚本失败:', err)
  amapMcpClient.close()
  amapMcpProcess.stop()
  process.exit(1)
})
