import { ChromaClient, Collection } from 'chromadb'

const CHROMA_URL = process.env.CHROMA_URL || 'http://localhost:8000'
const COLLECTION_NAME = 'travel_spots'

let client: ChromaClient | null = null
let collection: Collection | null = null

function parseChromaUrl(url: string) {
  const parsed = new URL(url)
  return {
    host: parsed.hostname,
    port: parseInt(parsed.port || '8000', 10),
    ssl: parsed.protocol === 'https:',
  }
}

const dummyEmbedding = {
  name: 'local-bge',
  generate: async () => [[]] as number[][],
}

export function getChromaClient(): ChromaClient {
  if (!client) {
    const conn = parseChromaUrl(CHROMA_URL)
    client = new ChromaClient({
      host: conn.host,
      port: conn.port,
      ssl: conn.ssl,
    })
  }
  return client
}

export async function getSpotsCollection(): Promise<Collection> {
  if (collection) return collection

  const cli = getChromaClient()
  collection = await cli.getOrCreateCollection({
    name: COLLECTION_NAME,
    metadata: { 'hnsw:space': 'cosine' },
    embeddingFunction: dummyEmbedding,
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
