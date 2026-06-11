import { randomUUID } from 'crypto'
import prisma from '../config/database'
import { getSpotsCollection, checkChromaHealth } from '../config/chroma'
import { embedText } from '../config/embeddings'
import { SpotInput, SpotInputSchema, SpotCategory } from '../types/agent'

/**
 * 创建景点（事务性同步 MySQL + Chroma）
 */
export async function createSpot(input: SpotInput) {
  const validated = SpotInputSchema.parse(input)
  const vectorId = randomUUID()

  const spot = await prisma.spot.create({
    data: {
      name: validated.name,
      city: validated.city,
      category: validated.category,
      description: validated.description,
      tags: validated.tags,
      avgCost: validated.avgCost,
      duration: validated.duration,
      openTime: validated.openTime,
      rating: validated.rating,
      vectorId,
    },
  })

  try {
    const collection = await getSpotsCollection()
    const embedding = await embedText(validated.description)
    await collection.add({
      ids: [vectorId],
      embeddings: [embedding],
      documents: [validated.description],
      metadatas: [{
        city: validated.city,
        name: validated.name,
        category: validated.category,
        tags: JSON.stringify(validated.tags),
        rating: validated.rating ?? 0,
      }],
    })
  } catch (e) {
    await prisma.spot.delete({ where: { id: spot.id } })
    console.error('[Knowledge] Chroma 同步失败，已回滚:', e)
    throw new Error('知识库同步失败，请稍后重试')
  }

  return spot
}

/**
 * 检索景点（优先 Chroma，失败降级为 MySQL LIKE）
 */
export async function searchSpots(params: {
  query: string
  city: string
  category?: SpotCategory
  limit?: number
}): Promise<string> {
  const { query, city, category, limit = 5 } = params

  const chromaAvailable = await checkChromaHealth()
  if (chromaAvailable) {
    try {
      const collection = await getSpotsCollection()
      const queryEmbedding = await embedText(query)
      const where: Record<string, unknown> = { city }
      if (category) where.category = category

      const results = await collection.query({
        queryEmbeddings: [queryEmbedding],
        nResults: limit,
        where,
      })

      const docs = results.documents?.[0] || []
      if (docs.length > 0) {
        return docs.join('\n---\n')
      }
      console.warn('[Knowledge] Chroma 检索为空，降级到 MySQL')
    } catch (e) {
      console.warn('[Knowledge] Chroma 检索失败，降级到 MySQL:', e)
    }
  } else {
    console.warn('[Knowledge] Chroma 不可用，降级到 MySQL')
  }

  const where: { city: string; category?: string } = { city }
  if (category) where.category = category
  const spots = await prisma.spot.findMany({
    where,
    take: limit,
    orderBy: { rating: 'desc' },
  })
  return spots.map(s => s.description).join('\n---\n')
}

/**
 * 列出景点
 */
export async function listSpots(params: { city?: string; category?: SpotCategory; page?: number; pageSize?: number }) {
  const { city, category, page = 1, pageSize = 20 } = params
  const where: { city?: string; category?: string } = {}
  if (city) where.city = city
  if (category) where.category = category
  const [items, total] = await Promise.all([
    prisma.spot.findMany({ where, skip: (page - 1) * pageSize, take: pageSize, orderBy: { createdAt: 'desc' } }),
    prisma.spot.count({ where }),
  ])
  return { items, total, page, pageSize }
}

/**
 * 批量导入（用于 seed 脚本）
 */
export async function bulkImportSpots(spots: SpotInput[]) {
  let success = 0
  let failed = 0
  for (const spot of spots) {
    try {
      await createSpot(spot)
      success++
    } catch (e) {
      console.error(`[Knowledge] 导入失败: ${spot.name}`, e instanceof Error ? e.message : e)
      failed++
    }
  }
  return { success, failed, total: spots.length }
}
