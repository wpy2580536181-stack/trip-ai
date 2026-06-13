import { readFileSync, readdirSync } from 'fs'
import { join } from 'path'
import { bulkImportSpots } from '../src/services/knowledgeService'
import { SpotInput } from '../src/types/agent'

async function main() {
  console.log('=== 知识库导入脚本 ===')
  const dataDir = join(__dirname, '..', 'data', 'spots')

  // 自动发现所有城市 JSON 文件
  const files = readdirSync(dataDir).filter(f => f.endsWith('.json')).sort()
  console.log(`发现 ${files.length} 个城市数据: ${files.join(', ')}`)

  let totalSuccess = 0
  let totalFailed = 0

  for (const file of files) {
    const cityName = file.replace('.json', '')
    const filePath = join(dataDir, file)
    try {
      const raw = readFileSync(filePath, 'utf-8')
      const spots: SpotInput[] = JSON.parse(raw)
      console.log(`\n>>> 导入 ${cityName} (${spots.length} 个 Spot)...`)
      const result = await bulkImportSpots(spots)
      console.log(`   成功: ${result.success}, 失败: ${result.failed}`)
      totalSuccess += result.success
      totalFailed += result.failed
    } catch (e) {
      console.error(`   跳过 ${file}: ${e instanceof Error ? e.message : e}`)
    }
  }

  console.log(`\n=== 完成 === 总成功: ${totalSuccess}, 总失败: ${totalFailed}`)
  process.exit(0)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
