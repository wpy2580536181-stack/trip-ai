import { readFileSync } from 'fs'
import { join } from 'path'
import { bulkImportSpots } from '../src/services/knowledgeService'
import { SpotInput } from '../src/types/agent'

async function main() {
  console.log('=== 知识库导入脚本 ===')
  const dataDir = join(__dirname, '..', 'data', 'spots')
  const cities = ['chengdu']

  let totalSuccess = 0
  let totalFailed = 0

  for (const city of cities) {
    const filePath = join(dataDir, `${city}.json`)
    try {
      const raw = readFileSync(filePath, 'utf-8')
      const spots: SpotInput[] = JSON.parse(raw)
      console.log(`\n>>> 导入 ${city}.json (${spots.length} 个景点)...`)
      const result = await bulkImportSpots(spots)
      console.log(`   成功: ${result.success}, 失败: ${result.failed}`)
      totalSuccess += result.success
      totalFailed += result.failed
    } catch (e) {
      console.error(`   跳过 ${city}.json: ${e instanceof Error ? e.message : e}`)
    }
  }

  console.log(`\n=== 完成 === 总成功: ${totalSuccess}, 总失败: ${totalFailed}`)
  process.exit(0)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
