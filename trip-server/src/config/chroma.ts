import { ChromaClient, Collection } from 'chromadb'

const CHROMA_URL = process.env.CHROMA_URL || 'http://localhost:8000'
const COLLECTION_NAME = 'travel_spots'

let client: ChromaClient | null = null
let collection: Collection | null = null

export function getChromaClient(): ChromaClient {
  if (!client) {
    client = new ChromaClient({ path: CHROMA_URL })
  }
  return client
}

export async function getSpotsCollection(): Promise<Collection> {
  if (collection) return collection

  const cli = getChromaClient()
  collection = await cli.getOrCreateCollection({
    name: COLLECTION_NAME,
    metadata: { 'hnsw:space': 'cosine' },
  })
  return collection
}

export async function checkChromaHealth(): Promise<boolean> {
  try {
    const cli = getChromaClient()
    await cli.heartbeat()
    return true
  } catch (e) {
    console.error('[Chroma] 健康检查失败:', e instanceof Error ? e.message : e)
    return false
  }
}
