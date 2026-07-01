/**
 * 从 MySQL 批量重索引 Chroma
 * 用法: npx tsx scripts/chroma-reindex.ts
 */
import prisma from '../src/config/database'
import { getSpotsCollection } from '../src/config/chroma'
import { embedText } from '../src/config/embeddings'

const BATCH = 100

async function main() {
  console.log('=== Chroma 重索引 ===\n')

  const collection = await getSpotsCollection()
  const existing = await collection.get()
  const existingIds = new Set(existing.ids || [])
  console.log(`Chroma 现有: ${existingIds.size} 条`)

  const spots = await prisma.spot.findMany({
    where: existingIds.size > 0 ? { vectorId: { notIn: [...existingIds] } } : {},
    orderBy: { id: 'asc' },
  })
  console.log(`需写入: ${spots.length} 条\n`)

  let done = 0
  for (let i = 0; i < spots.length; i += BATCH) {
    const batch = spots.slice(i, i + BATCH)
    const embeddings = await Promise.all(
      batch.map(s => embedText(
        `${s.city} ${s.name} ${s.description} ${JSON.stringify(s.tags)} ${s.category}`
      ))
    )
    await collection.add({
      ids: batch.map(s => s.vectorId!),
      embeddings,
      documents: batch.map(s =>
        `${s.city} ${s.name} ${s.description} ${JSON.stringify(s.tags)}`
      ),
      metadatas: batch.map(s => ({
        city: s.city,
        name: s.name,
        category: s.category,
        tags: JSON.stringify(s.tags),
        rating: s.rating ?? 0,
      })),
    })
    done += batch.length
    console.log(`  ${done}/${spots.length}`)
  }

  const final = await collection.count()
  console.log(`\nChroma 总数: ${final}`)
  await prisma.$disconnect()
}

main().catch(e => { console.error(e); process.exit(1) })
