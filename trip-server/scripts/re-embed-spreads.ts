/**
 * 重 embedding 迁移脚本
 * 将现有 754 条 Spot 从旧格式（仅 description）升级为多字段拼接格式。
 *
 * 用法: npx ts-node scripts/re-embed-spreads.ts
 */
import prisma from '../src/config/database'
import { getSpotsCollection } from '../src/config/chroma'
import { embedText } from '../src/config/embeddings'

type SpotRow = {
  id: number
  name: string
  city: string
  category: string
  description: string
  tags: unknown
  vectorId: string | null
}

function buildDocument(spot: SpotRow): string {
  const tags = Array.isArray(spot.tags) ? spot.tags.join(' ') : ''
  return `${spot.city} ${spot.name} ${spot.description} ${tags} ${spot.category}`
}

async function main() {
  console.log('[Re-embed] 开始迁移...')

  // 1. 读取全部 Spot
  const spots: SpotRow[] = await prisma.$queryRaw<SpotRow[]>`
    SELECT id, name, city, category, description, tags, vector_id as vectorId
    FROM spots
  `
  console.log(`[Re-embed] 共 ${spots.length} 条数据`)

  const skipped: number[] = []
  const success: number[] = []
  const failed: Array<{ id: number; name: string; error: string }> = []

  // 2. 获取 Chroma collection
  const collection = await getSpotsCollection()

  // 3. 逐条重 embedding
  const batchSize = 10
  for (let i = 0; i < spots.length; i += batchSize) {
    const batch = spots.slice(i, i + batchSize)
    const promises = batch.map(async (spot) => {
      if (!spot.vectorId) {
        skipped.push(spot.id)
        return
      }
      try {
        const docText = buildDocument(spot)
        const embedding = await embedText(docText)

        await collection.update({
          ids: [spot.vectorId],
          embeddings: [embedding],
          documents: [docText],
        })

        success.push(spot.id)
        if ((i + batch.indexOf(spot) + 1) % 50 === 0) {
          console.log(`[Re-embed] 进度: ${i + batch.indexOf(spot) + 1}/${spots.length}`)
        }
      } catch (e) {
        failed.push({
          id: spot.id,
          name: spot.name,
          error: e instanceof Error ? e.message : String(e),
        })
      }
    })
    await Promise.all(promises)
  }

  // 4. 报告
  console.log('\n========== 迁移报告 ==========')
  console.log(`成功: ${success.length}`)
  console.log(`跳过 (无 vectorId): ${skipped.length}`)
  console.log(`失败: ${failed.length}`)
  if (failed.length > 0) {
    console.log('\n失败详情:')
    failed.forEach(f => console.log(`  - #${f.id} ${f.name}: ${f.error}`))
  }
  console.log('==============================')

  // 关闭连接
  await prisma.$disconnect()
  process.exit(failed.length > 0 ? 1 : 0)
}

main().catch((e) => {
  console.error('[Re-embed] 迁移失败:', e)
  prisma.$disconnect()
  process.exit(1)
})
