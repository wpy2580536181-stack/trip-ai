import { readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import { bulkImportSpots } from '../src/services/knowledgeService'
import type { SpotInput } from '../src/types/agent'

interface AmapPoi {
  name: string
  address: string
  type: string
  adname: string
  pname: string
}

interface AmapCityData {
  city: string
  scenic: AmapPoi[]
  food: AmapPoi[]
  hotel: AmapPoi[]
}

function extractTags(type: string): string[] {
  return type.split(';').filter(Boolean).slice(-2)
}

function buildDescription(poi: AmapPoi, city: string): string {
  const parts = [poi.name]
  if (poi.address) parts.push(`位于${poi.address}`)
  if (poi.adname && poi.adname !== city) parts.push(`${poi.adname}`)
  const tags = extractTags(poi.type)
  if (tags.length > 0) parts.push(`类型${tags.join(' ')}`)
  return parts.join('，') + '。'
}

const CATEGORY_MAP: Record<string, 'attraction' | 'food' | 'hotel'> = {
  scenic: 'attraction',
  food: 'food',
  hotel: 'hotel',
}

async function main() {
  console.log('=== POI 知识库导入脚本 ===')
  const dataDir = join(__dirname, '..', 'data', 'poi_raw')
  const files = readdirSync(dataDir).filter(f => f.endsWith('.json')).sort()
  console.log(`发现 ${files.length} 个城市数据\n`)

  let totalSuccess = 0
  let totalFailed = 0

  for (const file of files) {
    const filePath = join(dataDir, file)
    const raw = readFileSync(filePath, 'utf-8')
    const data: AmapCityData = JSON.parse(raw)
    const spots: SpotInput[] = []

    for (const [rawCategory, items] of Object.entries(data)) {
      if (!Array.isArray(items)) continue
      const category = CATEGORY_MAP[rawCategory]
      if (!category) continue

      for (const poi of items) {
        spots.push({
          name: poi.name.slice(0, 100),
          city: data.city,
          category,
          description: buildDescription(poi, data.city).slice(0, 500),
          tags: extractTags(poi.type),
        })
      }
    }

    if (spots.length === 0) {
      console.log(`  ${file}: 无可导入的数据`)
      continue
    }

    console.log(`>>> ${data.city} (${spots.length} 条)`)
    const result = await bulkImportSpots(spots)
    console.log(`   成功: ${result.success}, 失败: ${result.failed}`)
    totalSuccess += result.success
    totalFailed += result.failed
  }

  console.log(`\n=== 完成 === 总成功: ${totalSuccess}, 总失败: ${totalFailed}`)
  process.exit(0)
}

main().catch(e => {
  console.error('FAIL:', e)
  process.exit(1)
})
