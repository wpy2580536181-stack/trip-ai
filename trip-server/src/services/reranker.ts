/**
 * Cross-Encoder Reranker 服务
 * 对召回的候选文档做精细重排序。
 *
 * 使用本地 bge-reranker-v2-minicml 模型（~250MB），
 * 输入 query + 文档对，输出相关性得分。
 *
 * bge-reranker 是 SequenceClassification 模型：
 * tokenizer(query, { text_pair: doc }) → model → logits → sigmoid → score
 */
import { env, AutoTokenizer, AutoModelForSequenceClassification } from '@xenova/transformers'

const HF_MIRROR = process.env.HF_ENDPOINT || 'https://hf-mirror.com/'
env.remoteHost = HF_MIRROR
env.remotePathTemplate = '{model}/resolve/{revision}/'

const RERANKER_MODEL = 'Xenova/bge-reranker-base'

let tokenizerInstance: Awaited<ReturnType<typeof AutoTokenizer.from_pretrained>> | null = null
let modelInstance: Awaited<ReturnType<typeof AutoModelForSequenceClassification.from_pretrained>> | null = null

async function getTokenizer() {
  if (!tokenizerInstance) {
    console.log(`[Reranker] 正在加载 tokenizer ${RERANKER_MODEL}...`)
    tokenizerInstance = await AutoTokenizer.from_pretrained(RERANKER_MODEL)
    console.log(`[Reranker] tokenizer 加载完成`)
  }
  return tokenizerInstance
}

async function getModel() {
  if (!modelInstance) {
    console.log(`[Reranker] 正在加载模型 ${RERANKER_MODEL}...`)
    modelInstance = await AutoModelForSequenceClassification.from_pretrained(RERANKER_MODEL)
    console.log(`[Reranker] 模型加载完成`)
  }
  return modelInstance
}

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x))
}

export type ScoredDocument = {
  text: string
  score: number
}

/**
 * 对多个候选文档做 reranking
 */
export async function rerank(
  query: string,
  documents: string[],
): Promise<ScoredDocument[]> {
  if (documents.length === 0) return []

  try {
    const tokenizer = await getTokenizer()
    const model = await getModel()

    // 逐对评分（Cross-Encoder 不支持真正的 batch）
    const scores: Array<{ text: string; score: number }> = []
    for (const doc of documents) {
      const encoded = await tokenizer(query, {
        text_pair: doc,
        truncation: true,
        return_tensors: false,
      })

      const outputs = await model(encoded)

      // logits 形状: [1, 1]
      const score = Array.from(outputs.logits?.data as Float32Array)?.[0] ?? 0
      scores.push({ text: doc, score: sigmoid(score) })
    }

    return scores.sort((a, b) => b.score - a.score)
  } catch (e) {
    console.warn('[Reranker] 重排序失败，使用原始排序:', e instanceof Error ? e.message : e)
    return documents.map(doc => ({ text: doc, score: 0 }))
  }
}

/**
 * 取 rerank 后的 top-K
 */
export async function rerankTopK(
  query: string,
  documents: string[],
  k: number,
): Promise<ScoredDocument[]> {
  const scored = await rerank(query, documents)
  return scored.slice(0, k)
}
