import { randomUUID } from 'crypto'
import prisma from '../config/database'
import { getSpotsCollection, checkChromaHealth } from '../config/chroma'
import { embedText } from '../config/embeddings'
import { rewriteQuery } from './queryRewriter'
import { rerankTopK } from './reranker'
import { SpotInput, SpotInputSchema, SpotCategory } from '../types/agent'
import { knowledgeLog as log } from '../utils/logger'

/**
 * 构建 embedding 文档：拼接多字段以提升检索质量。
 * 城市名和名称放在最前面，因为 embedding 模型对序列开头的位置最敏感。
 */
function buildEmbeddingDocument(spot: SpotInput): string {
  const tags = Array.isArray(spot.tags) ? spot.tags.join(' ') : ''
  return `${spot.city} ${spot.name} ${spot.description} ${tags} ${spot.category}`
}

/**
 * 创建景点（MySQL 优先，Chroma 异步补充）
 * 如果 Chroma 不可用，数据仍写入 MySQL，仅记录警告。
 */
export async function createSpot(input: SpotInput) {
  const validated = SpotInputSchema.parse(input)
  const vectorId = randomUUID()
  const docText = buildEmbeddingDocument(validated)

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

  // Chroma 写入失败时不阻塞，仅记录警告
  try {
    const collection = await getSpotsCollection()
    const embedding = await embedText(docText)
    await collection.add({
      ids: [vectorId],
      embeddings: [embedding],
      documents: [docText],
      metadatas: [{
        city: validated.city,
        name: validated.name,
        category: validated.category,
        tags: JSON.stringify(validated.tags),
        rating: validated.rating ?? 0,
      }],
    })
  } catch (e) {
    log.warn({ err: e }, 'Chroma 写入失败（MySQL 数据已保存）')
  }

  return spot
}

/**
 * 关键词提取：从 query 中切分 2-4 字关键词用于 LIKE 检索
 */
function extractKeywords(query: string): string[] {
  // 简单策略：移除停用词，保留 2-5 个字符的片段
  const stopWords = new Set(['什么', '怎么', '哪里', '去了', '好玩', '好吃', '好看', '推荐', '请问', '我想', '需要', '可以', '一下', '一下', '吧', '啊', '呢', '吗', '了', '的', '了', '在', '有'])
  const keywords: string[] = []
  // 先尝试 4-gram / 3-gram / 2-gram 滑动窗口
  for (let len = 5; len >= 2; len--) {
    for (let i = 0; i <= query.length - len; i++) {
      const chunk = query.slice(i, i + len)
      if (/[一-龥]{2,}/.test(chunk) && !stopWords.has(chunk)) {
        keywords.push(chunk)
      }
    }
  }
  // 去重，最多保留 5 个
  return [...new Set(keywords)].slice(0, 5)
}

/**
 * 修复 P2-8：检查 spots 表是否存在 FULLTEXT 索引，结果缓存
 */
let fulltextCache: boolean | null = null
async function hasFulltextIndex(): Promise<boolean> {
  if (fulltextCache !== null) return fulltextCache
  try {
    const rows: Array<{ count: number }> = await prisma.$queryRawUnsafe(
      `SELECT COUNT(*) AS count FROM information_schema.STATISTICS
       WHERE table_schema = DATABASE() AND table_name = 'spots' AND index_name = 'ft_name_desc'`,
    ) as any
    fulltextCache = (rows[0]?.count ?? 0) > 0
  } catch {
    fulltextCache = false
  }
  return fulltextCache
}

/**
 * MySQL 关键词检索（参数化查询，防 SQL 注入）
 * 修复 P2-8：优先用 FULLTEXT 索引，索引不存在时回退 LIKE
 */
async function mysqlKeywordSearch(params: {
  city: string
  keywords: string[]
  category?: SpotCategory
  limit: number
}): Promise<{ desc: string; name: string; category: string; rating: number | null }[]> {
  const { city, keywords, category, limit } = params
  if (keywords.length === 0) return []

  const useFulltext = await hasFulltextIndex()

  if (useFulltext) {
    // 修复 P2-8：MATCH AGAINST 走 FULLTEXT 索引，性能远超 LIKE
    const fulltextExpr = keywords
      .map(() => 'MATCH(name, description) AGAINST (? IN NATURAL LANGUAGE MODE)')
      .join(' OR ')
    const fulltextArgs = [...keywords]

    let whereClause = `(${fulltextExpr})`
    const sqlArgs: string[] = [...fulltextArgs]

    if (category) {
      whereClause = `city = ? AND category = ? AND ${whereClause}`
      sqlArgs.unshift(category)
    }
    sqlArgs.unshift(city)

    const sql = `SELECT name, description, category, rating FROM spots WHERE city = ? AND ${whereClause} ORDER BY rating DESC LIMIT ?`
    sqlArgs.push(String(limit))

    try {
      const results: Array<{ name: string; description: string; category: string; rating: number | null }> =
        await prisma.$queryRawUnsafe(sql, ...sqlArgs) as any
      return results.map(r => ({ desc: r.description, name: r.name, category: r.category, rating: r.rating }))
    } catch (e) {
      log.warn({ err: e }, 'FULLTEXT 查询失败，回退 LIKE')
    }
  }

  // LIKE 回退路径
  const whereParts: string[] = []
  const allArgs: string[] = []

  for (const kw of keywords) {
    whereParts.push('(name LIKE CONCAT("%", ?, "%") OR description LIKE CONCAT("%", ?, "%"))')
    allArgs.push(kw, kw)
  }

  let whereClause = `(${whereParts.join(' OR ')})`
  let sqlArgs: string[] = [...allArgs]

  if (category) {
    whereClause = `city = ? AND category = ? AND ${whereClause}`
    sqlArgs = [city, category, ...sqlArgs]
  } else {
    whereClause = `city = ? AND ${whereClause}`
    sqlArgs = [city, ...sqlArgs]
  }
  const sql = `SELECT name, description, category, rating FROM spots WHERE ${whereClause} ORDER BY rating DESC LIMIT ?`
  const args = [...sqlArgs, String(limit)]
  const results: Array<{ name: string; description: string; category: string; rating: number | null }> = await prisma.$queryRawUnsafe(sql, ...args) as any
  return results.map(r => ({ desc: r.description, name: r.name, category: r.category, rating: r.rating }))
}

/** 搜索结果结构化数据 */
type ResultItem = { name: string; desc: string; category: string; rating: number | null }

/** RRF 排序增强 */
type ResultWithRank = ResultItem & { rrfScore: number }

/**
 * RRF (Reciprocal Rank Fusion) 融合排序
 * 对多路召回结果按排名融合：score = Σ 1 / (rank + K)，K 默认 60
 */
const RRF_K = 60

function rrfFuse(path1: ResultItem[], path2: ResultItem[], path3: ResultItem[]): ResultWithRank[] {
  const scoreMap = new Map<string, { score: number; item: ResultItem }>()

  const addPath = (items: ResultItem[]) => {
    items.forEach((item, rank) => {
      const existing = scoreMap.get(item.name)
      if (existing) {
        existing.score += 1 / (rank + RRF_K)
      } else {
        scoreMap.set(item.name, { score: 1 / (rank + RRF_K), item })
      }
    })
  }

  addPath(path1)
  addPath(path2)
  addPath(path3)

  return Array.from(scoreMap.values())
    .map(({ score, item }) => ({ ...item, rrfScore: score }))
    .sort((a, b) => b.rrfScore - a.rrfScore)
}

/**
 * MySQL 分类 + rating 排序检索（参数化查询，防 SQL 注入）
 */
async function mysqlRatingSearch(params: {
  city: string
  category?: SpotCategory
  limit: number
}): Promise<ResultItem[]> {
  const { city, category, limit } = params
  let sql: string
  let args: string[]

  if (category) {
    sql = 'SELECT name, description, category, rating FROM spots WHERE city = ? AND category = ? ORDER BY rating DESC LIMIT ?'
    args = [city, category, String(limit)]
  } else {
    sql = 'SELECT name, description, category, rating FROM spots WHERE city = ? ORDER BY rating DESC LIMIT ?'
    args = [city, String(limit)]
  }

  const results: Array<{ name: string; description: string; category: string; rating: number | null }> = await prisma.$queryRawUnsafe(sql, ...args) as any
  return results.map(r => ({ name: r.name, desc: r.description, category: r.category, rating: r.rating }))
}

/**
 * 检索景点（三路并行召回 + RRF 融合）
 * 路径 1: Chroma 向量检索（top-20）
 * 路径 2: MySQL LIKE 关键词检索（top-10）
 * 路径 3: MySQL rating 排序（top-10）
 * → RRF 融合去重 → 取前 limit 条
 */
export async function searchSpots(params: {
  query: string
  city: string
  category?: SpotCategory
  limit?: number
}): Promise<string> {
  const { query, city, category, limit = 5 } = params

  // === 查询改写：LLM 将自然语言转为检索关键词 ===
  const rewrittenQuery = await rewriteQuery(query)
  if (rewrittenQuery !== query) {
    log.debug({ original: query, rewritten: rewrittenQuery }, 'query rewritten')
  }

  // === 三路并行召回 ===
  const chromaAvailable = await checkChromaHealth()
  let path1: ResultItem[] = [] // Chroma 向量
  let path2: ResultItem[] = [] // MySQL LIKE
  let path3: ResultItem[] = [] // MySQL rating

  if (chromaAvailable) {
    // --- 路径 1: Chroma 向量检索 ---
    try {
      const collection = await getSpotsCollection()
      const queryEmbedding = await embedText(rewrittenQuery)
      const where: Record<string, unknown> = category
        ? { $and: [{ city }, { category }] }
        : { city }

      const results = await collection.query({
        queryEmbeddings: [queryEmbedding],
        nResults: 20,
        where: where as any,
      })

      const docs = results.documents?.[0] || []
      const metadatas = results.metadatas?.[0] || []
      for (let i = 0; i < docs.length; i++) {
        const meta = metadatas[i] || {}
        const name = (meta.name as string) || '未知'
        path1.push({
          name,
          desc: (docs[i] as string) || '',
          category: (meta.category as string) || '',
          rating: (meta.rating as number) ?? null,
        })
      }
    } catch (e) {
      log.warn({ err: e }, 'Chroma 检索失败，降级到 MySQL')
    }
  } else {
    log.warn('Chroma 不可用，降级到 MySQL')
  }

  // --- 路径 2: MySQL LIKE 关键词检索 ---
  try {
    const keywords = extractKeywords(query)
    const kwResults = await mysqlKeywordSearch({ city, keywords, category, limit: 10 })
    path2 = kwResults.map(r => ({ name: r.name, desc: r.desc, category: r.category, rating: r.rating }))
  } catch (e) {
    log.warn({ err: e }, 'MySQL 关键词检索失败')
  }

  // --- 路径 3: MySQL rating 排序 ---
  try {
    path3 = await mysqlRatingSearch({ city, category, limit: 10 })
  } catch (e) {
    log.warn({ err: e }, 'MySQL rating 检索失败')
  }

  // === RRF 融合 ===
  const fused = rrfFuse(path1, path2, path3)

  // === Cross-Encoder 重排序（对 top-20 候选精排） ===
  const rerankCandidates = fused.slice(0, 20)
  if (rerankCandidates.length > 1) {
    try {
      const reranked = await rerankTopK(
        rewrittenQuery,
        rerankCandidates.map(c => c.desc),
        Math.min(fused.length, 20),
      )
      // 按 rerank 得分重新映射
      const rerankedMap = new Map<string, number>()
      reranked.forEach((r, idx) => { rerankedMap.set(r.text, idx) })
      const rerankedItems = rerankCandidates
        .sort((a, b) => (rerankedMap.get(a.desc) ?? fused.indexOf(a)) - (rerankedMap.get(b.desc) ?? fused.indexOf(b)))
        .slice(0, limit)

      // 格式化输出
      return rerankedItems.map((item, idx) => {
        const ratingStr = item.rating ? `${item.rating}分` : ''
        const categoryStr = item.category ? `[${item.category}]` : ''
        return `${idx + 1}. ${item.name} ${categoryStr} ${ratingStr}\n${item.desc}`
      }).join('\n---\n')
    } catch (e) {
      log.warn({ err: e }, 'Reranker 失败，使用 RRF 排序')
      // 降级：使用 RRF 排序结果
    }
  }

  const finalItems = fused.slice(0, limit)

  if (finalItems.length === 0) {
    return '(未找到相关景点)'
  }

  // 格式化输出
  return finalItems.map((item, idx) => {
    const ratingStr = item.rating ? `${item.rating}分` : ''
    const categoryStr = item.category ? `[${item.category}]` : ''
    return `${idx + 1}. ${item.name} ${categoryStr} ${ratingStr}\n${item.desc}`
  }).join('\n---\n')
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
      log.error({ err: e, spotName: spot.name }, '导入失败')
      failed++
    }
  }
  return { success, failed, total: spots.length }
}

/**
 * 更新景点
 */
export async function updateSpot(id: number, input: Partial<SpotInput>) {
  const existing = await prisma.spot.findUnique({ where: { id } })
  if (!existing) throw new Error('景点不存在')

  const data: any = {}
  if (input.name !== undefined) data.name = input.name
  if (input.city !== undefined) data.city = input.city
  if (input.category !== undefined) data.category = input.category
  if (input.description !== undefined) data.description = input.description
  if (input.tags !== undefined) data.tags = input.tags
  if (input.avgCost !== undefined) data.avgCost = input.avgCost
  if (input.duration !== undefined) data.duration = input.duration
  if (input.openTime !== undefined) data.openTime = input.openTime
  if (input.rating !== undefined) data.rating = input.rating

  const updated = await prisma.spot.update({ where: { id }, data })

  // 同步 Chroma
  try {
    const collection = await getSpotsCollection()
    if (existing.vectorId) {
      await collection.delete({ ids: [existing.vectorId] })
    }
    const embedding = await embedText(updated.description)
    const vectorId = existing.vectorId || `spot_${id}`
    await collection.add({
      ids: [vectorId],
      embeddings: [embedding],
      documents: [updated.description],
      metadatas: [{
        city: updated.city,
        name: updated.name,
        category: updated.category,
        tags: JSON.stringify(updated.tags),
        rating: updated.rating ?? 0,
      }],
    })
    if (!existing.vectorId) {
      await prisma.spot.update({ where: { id }, data: { vectorId } })
    }
  } catch (e) {
    log.warn({ err: e }, 'Chroma 同步失败（MySQL 已更新）')
  }

  return updated
}

/**
 * 删除景点
 */
export async function deleteSpot(id: number) {
  const existing = await prisma.spot.findUnique({ where: { id } })
  if (!existing) throw new Error('景点不存在')

  await prisma.spot.delete({ where: { id } })

  try {
    if (existing.vectorId) {
      const collection = await getSpotsCollection()
      await collection.delete({ ids: [existing.vectorId] })
    }
  } catch (e) {
    log.warn({ err: e }, 'Chroma 删除同步失败（MySQL 已删除）')
  }
}
