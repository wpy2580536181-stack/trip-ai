/**
 * POI 转换 + 导入脚本
 *
 * 流程：
 * 1. 读取 data/poi_raw/{城市}.json（高德原始 POI）
 * 2. 按类别分组（scenic→attraction, food→food, hotel→hotel）
 * 3. 对每个 POI 调用 DeepSeek LLM 生成 description/tags/rating
 * 4. 输出为 data/spots/{城市}.json（项目 SpotInput 格式）
 * 5. 调用 seed-knowledge 的 bulkImportSpots 写入 MySQL + Chroma
 */
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'fs'
import { join, dirname } from 'path'

const PROJECT_ROOT = dirname(require.resolve('../package.json'))

// Load .env
function loadEnv() {
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
}
loadEnv()

const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY || ''
const DEEPSEEK_BASE_URL = process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1'
const DEEPSEEK_MODEL = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash'

if (!DEEPSEEK_API_KEY) {
  console.error('[Error] DEEPSEEK_API_KEY not set')
  process.exit(1)
}

// ─── 类型映射 ───────────────────────────────────────────────

const CATEGORY_MAP: Record<string, string> = {
  scenic: 'attraction',
  food: 'food',
  hotel: 'hotel',
}

interface RawPOI {
  name: string
  typecode: string
  type: string
  address: string
  location: string
  id: string
  adname: string
}

interface RawCityData {
  city: string
  scenic: RawPOI[]
  food: RawPOI[]
  hotel: RawPOI[]
}

// LLM 输出的 Spot 对象
interface LLMSpot {
  name: string
  city: string
  category: 'attraction' | 'food' | 'hotel' | 'transport'
  description: string
  tags: string[]
  avgCost: number
  duration?: string
  openTime?: string
  rating: number
}

// ─── LLM 调用 ──────────────────────────────────────────────

async function generateSpotDescription(poi: RawPOI, category: string): Promise<LLMSpot> {
  const systemPrompt = `你是一个旅游数据标注助手。根据 POI 信息，生成结构化景点数据。

要求：
- description: 100-300 字详细描述，包含历史背景、特色、适合人群、游览建议等，语言优美但准确
- tags: 2-4 个标签
- avgCost: 平均花费（元），景点/酒店填实际价格，美食填人均，不确定的填 0
- duration: 建议游玩时长
- openTime: 营业时间，不确定填"全天"
- rating: 0-5 的评分，热门景点 4.0-5.0，一般景点 3.5-4.5

直接返回 JSON，格式：
{
  "name": "原 POI 名称",
  "city": "城市名",
  "category": "类别",
  "description": "详细描述",
  "tags": ["标签1", "标签2"],
  "avgCost": 0,
  "duration": "建议时长",
  "openTime": "营业时间",
  "rating": 4.5
}

注意：description 必须有价值，不能只是重复名称。只返回 JSON 对象，不要加 markdown 代码块标记。`

  const userPrompt = `POI 名称：${poi.name}
类别：${category}
类型：${poi.type}
地址：${poi.address}
区域：${poi.adname}`

  const url = `${DEEPSEEK_BASE_URL}/chat/completions`

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${DEEPSEEK_API_KEY}`,
    },
    body: JSON.stringify({
      model: DEEPSEEK_MODEL,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: 0.7,
      max_tokens: 500,
    }),
  })

  if (!res.ok) {
    const errText = await res.text()
    throw new Error(`LLM API error: ${res.status} ${errText}`)
  }

  const data = await res.json() as { choices: [{ message: { content: string } }] }
  const content = data.choices[0]?.message?.content || ''

  // 尝试解析 JSON（可能包裹在 ```json ... ``` 中）
  let jsonStr = content.trim()
  const codeBlockMatch = jsonStr.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (codeBlockMatch) jsonStr = codeBlockMatch[1].trim()

  const spot = JSON.parse(jsonStr) as LLMSpot
  spot.city = poi.adname as LLMSpot['city'] // fallback

  return spot
}

// ─── 批量处理 ──────────────────────────────────────────────

async function processCity(filePath: string): Promise<LLMSpot[]> {
  const raw = JSON.parse(readFileSync(filePath, 'utf-8')) as RawCityData
  const city = raw.city
  console.log(`\n>>> 处理 ${city} (${raw.scenic.length + raw.food.length + raw.hotel.length} 个 POI)`)

  const spots: LLMSpot[] = []

  for (const category of ['scenic', 'food', 'hotel'] as const) {
    const mappedCategory = CATEGORY_MAP[category]
    const pois = raw[category]

    for (const poi of pois) {
      try {
        const spot = await generateSpotDescription(poi, mappedCategory)
        spot.city = city // 确保 city 正确
        spots.push(spot)
        console.log(`  ✓ ${poi.name} → ${mappedCategory} (rating: ${spot.rating})`)
      } catch (e) {
        console.error(`  ✗ ${poi.name} 转换失败: ${e instanceof Error ? e.message : e}`)
        // 降级：用默认描述
        spots.push({
          name: poi.name,
          city,
          category: mappedCategory as LLMSpot['category'],
          description: poi.name + ' 是' + city + '的' + (mappedCategory === 'attraction' ? '旅游景点' : mappedCategory === 'food' ? '美食餐厅' : '住宿地点') + '，位于' + poi.adname + '。地址：' + poi.address,
          tags: [city],
          avgCost: 0,
          duration: '',
          openTime: '全天',
          rating: 3.5,
        })
      }
      // LLM 限频
      await sleep(1000)
    }
  }

  return spots
}

// ─── 主流程 ─────────────────────────────────────────────────

async function main() {
  console.log('=== POI 转换脚本 ===')

  const poiRawDir = join(PROJECT_ROOT, 'data', 'poi_raw')
  const spotsDir = join(PROJECT_ROOT, 'data', 'spots')
  mkdirSync(spotsDir, { recursive: true })

  // 读取所有城市文件
  const cityFiles = readdirSync(poiRawDir)
    .filter(f => f.endsWith('.json') && !f.startsWith('.'))
    .sort()

  console.log(`找到 ${cityFiles.length} 个城市原始数据`)

  const allSpotsByCity: Record<string, LLMSpot[]> = {}

  for (const file of cityFiles) {
    const cityName = file.replace('.json', '')
    const filePath = join(poiRawDir, file)

    try {
      const spots = await processCity(filePath)
      allSpotsByCity[cityName] = spots
    } catch (e) {
      console.error(`处理 ${cityName} 失败: ${e instanceof Error ? e.message : e}`)
    }
  }

  // 写入 spot JSON
  let totalConverted = 0
  for (const [cityName, spots] of Object.entries(allSpotsByCity)) {
    const outputPath = join(spotsDir, `${cityName}.json`)
    writeFileSync(outputPath, JSON.stringify(spots, null, 2), 'utf-8')
    console.log(`  → ${cityName}.json: ${spots.length} 个 Spot`)
    totalConverted += spots.length
  }

  console.log(`\n=== 完成 === 共转换 ${totalConverted} 个 Spot`)

  // 提示用户下一步
  console.log(`\n下一步：`)
  console.log(`1. 检查 ${spotsDir} 目录下的转换结果`)
  console.log(`2. 修改 seed-knowledge.ts 支持自动发现城市`)
  console.log(`3. 运行: cd trip-server && npx ts-node prisma/seed-knowledge.ts`)
  process.exit(0)
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
