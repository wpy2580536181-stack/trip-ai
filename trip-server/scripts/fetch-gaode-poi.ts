/**
 * 高德 POI 抓取脚本
 *
 * 从高德地图 v5/place/text 接口批量抓取国内热门旅游城市的 POI 数据。
 * 抓取三类：景点（keywords=景点）、美食（keywords=美食/特色菜）、住宿（keywords=酒店）。
 * region 参数保证结果落在目标城市内。
 * 原始数据输出到 data/poi_raw/{城市}.json。
 */
import { writeFileSync, mkdirSync, readFileSync } from 'fs'
import { join, dirname } from 'path'

const PROJECT_ROOT = dirname(require.resolve('../package.json'))
// Load .env
try {
  const envContent = readFileSync(join(PROJECT_ROOT, '.env'), 'utf-8')
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const idx = trimmed.indexOf('=')
    if (idx > 0) {
      const key = trimmed.substring(0, idx).trim()
      const val = trimmed.substring(idx + 1).trim()
      if (!process.env[key]) process.env[key] = val
    }
  }
} catch {}

const API_KEY = process.env.GAODE_API_KEY || ''
if (!API_KEY) {
  console.error('[Error] GAODE_API_KEY not set in .env')
  process.exit(1)
}

// ─── 城市列表 ───────────────────────────────────────────────

interface CityInfo {
  name: string
  region: string
}

const CITIES: CityInfo[] = [
  { name: '北京',   region: '110000' },
  { name: '上海',   region: '310000' },
  { name: '广州',   region: '440100' },
  { name: '深圳',   region: '440300' },
  { name: '杭州',   region: '330100' },
  { name: '南京',   region: '320100' },
  { name: '成都',   region: '510100' },
  { name: '重庆',   region: '500000' },
  { name: '西安',   region: '610100' },
  { name: '苏州',   region: '320500' },
  { name: '长沙',   region: '430100' },
  { name: '昆明',   region: '530100' },
  { name: '厦门',   region: '350200' },
  { name: '青岛',   region: '370200' },
  { name: '大连',   region: '210200' },
  { name: '天津',   region: '120000' },
  { name: '武汉',   region: '420100' },
  { name: '郑州',   region: '410100' },
  { name: '济南',   region: '370100' },
  { name: '福州',   region: '350100' },
  { name: '宁波',   region: '330200' },
  { name: '哈尔滨', region: '230100' },
  { name: '石家庄', region: '130100' },
  { name: '合肥',   region: '340100' },
  { name: '南昌',   region: '360100' },
  { name: '兰州',   region: '620100' },
  { name: '太原',   region: '140100' },
  { name: '贵阳',   region: '520100' },
  { name: '乌鲁木齐', region: '650100' },
  { name: '桂林',   region: '450300' },
]

// ─── API 调用 ───────────────────────────────────────────────

interface RawPOI {
  name: string
  typecode: string
  type: string
  address: string
  location: string
  id: string
  adname: string
}

async function searchPOI(keyword: string, region: string, pageSize: number = 25): Promise<RawPOI[]> {
  const params = new URLSearchParams({
    key: API_KEY,
    keywords: keyword,
    region,
    pageSize: String(pageSize),
    page: '1',
  })

  const url = `https://restapi.amap.com/v5/place/text?${params.toString()}`
  const res = await fetch(url)
  const data = await res.json() as { pois: RawPOI[], status: string, infocode: string }

  if (data.status !== '1' || data.infocode !== '10000') {
    return []
  }

  return data.pois
}

// ─── 去重 ───────────────────────────────────────────────────

function dedupPOIs(pois: RawPOI[]): RawPOI[] {
  const seen = new Set<string>()
  return pois.filter(poi => {
    const key = `${poi.name}|${poi.id}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

// 过滤：排除交通设施、停车场、公交站等
function isScenicPOI(poi: RawPOI): boolean {
  const exclude = ['地铁站', '公交站', '停车场', '服务区', '加油站', '收费站']
  return !exclude.some(e => poi.type.includes(e))
}

function isFoodPOI(poi: RawPOI): boolean {
  const exclude = ['地铁站', '公交站', '停车场', '酒店']
  // 餐饮必须是餐饮服务
  return poi.type.includes('餐饮服务') && !exclude.some(e => poi.type.includes(e))
}

function isHotelPOI(poi: RawPOI): boolean {
  return poi.type.includes('住宿服务') || poi.type.includes('宾馆') || poi.type.includes('酒店')
}

// ─── 主流程 ─────────────────────────────────────────────────

async function main() {
  console.log('=== 高德 POI 抓取脚本 ===')
  console.log(`城市数: ${CITIES.length}`)

  const outputDir = join(PROJECT_ROOT, 'data', 'poi_raw')
  mkdirSync(outputDir, { recursive: true })

  const resultsByCity: Record<string, { scenic: RawPOI[]; food: RawPOI[]; hotel: RawPOI[] }> = {}
  let totalFetched = 0

  for (const city of CITIES) {
    console.log(`\n>>> 抓取 ${city.name} ...`)
    resultsByCity[city.name] = { scenic: [], food: [], hotel: [] }

    // ── 景点：keywords=景点, pageSize=25 → 取前15条有效 ──
    const scenicPois: RawPOI[] = []
    const scenicRaw = await searchPOI('景点', city.region, 25)
    for (const p of scenicRaw) {
      if (isScenicPOI(p)) scenicPois.push(p)
      if (scenicPois.length >= 15) break
    }
    console.log(`  景点: ${scenicPois.length}/25 有效`)
    resultsByCity[city.name].scenic = dedupPOIs(scenicPois)
    totalFetched += scenicPois.length

    // ── 美食：keywords=美食+特色菜，取前10条 ──
    const foodPois: RawPOI[] = []
    const foodRaw = await searchPOI('美食 特色菜', city.region, 20)
    for (const p of foodRaw) {
      if (isFoodPOI(p)) foodPois.push(p)
      if (foodPois.length >= 10) break
    }
    console.log(`  美食: ${foodPois.length}/20 有效`)
    resultsByCity[city.name].food = dedupPOIs(foodPois)
    totalFetched += foodPois.length

    // ── 住宿：keywords=酒店，取前5条 ──
    const hotelPois: RawPOI[] = []
    const hotelRaw = await searchPOI('酒店 宾馆', city.region, 15)
    for (const p of hotelRaw) {
      if (isHotelPOI(p)) hotelPois.push(p)
      if (hotelPois.length >= 5) break
    }
    console.log(`  住宿: ${hotelPois.length}/15 有效`)
    resultsByCity[city.name].hotel = dedupPOIs(hotelPois)
    totalFetched += hotelPois.length

    await sleep(300)
  }

  // ── 写入原始数据 ──
  for (const [cityName, data] of Object.entries(resultsByCity)) {
    const filePath = join(outputDir, `${cityName}.json`)
    writeFileSync(filePath, JSON.stringify({
      city: cityName,
      scenic: data.scenic,
      food: data.food,
      hotel: data.hotel,
      summary: {
        scenic: data.scenic.length,
        food: data.food.length,
        hotel: data.hotel.length,
      }
    }, null, 2), 'utf-8')
    const total = data.scenic.length + data.food.length + data.hotel.length
    console.log(`  ✓ ${cityName}: ${total} POI (景点${data.scenic.length} 美食${data.food.length} 住宿${data.hotel.length})`)
  }

  console.log(`\n=== 完成 === 总抓取 POI: ${totalFetched}，输出 ${Object.keys(resultsByCity).length} 个城市`)
  process.exit(0)
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
