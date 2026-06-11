import { env, pipeline, FeatureExtractionPipeline } from '@xenova/transformers'

const HF_MIRROR = process.env.HF_ENDPOINT || 'https://hf-mirror.com/'
env.remoteHost = HF_MIRROR
env.remotePathTemplate = '{model}/resolve/{revision}/'
console.log(`[Embedding] 使用 HF endpoint: ${HF_MIRROR}`)

const MODEL_NAME = 'Xenova/bge-small-zh-v1.5'
const EMBEDDING_DIM = 512

let extractorPromise: Promise<FeatureExtractionPipeline> | null = null

export function getEmbedder(): Promise<FeatureExtractionPipeline> {
  if (!extractorPromise) {
    console.log(`[Embedding] 正在加载模型 ${MODEL_NAME}...`)
    extractorPromise = pipeline('feature-extraction', MODEL_NAME) as Promise<FeatureExtractionPipeline>
    extractorPromise.then(() => {
      console.log(`[Embedding] 模型加载完成`)
    }).catch((e) => {
      console.error(`[Embedding] 模型加载失败:`, e)
      extractorPromise = null
    })
  }
  return extractorPromise
}

export async function embedText(text: string): Promise<number[]> {
  const extractor = await getEmbedder()
  const result = await extractor(text, { pooling: 'mean', normalize: true })
  return Array.from(result.data as Float32Array)
}

export async function embedTexts(texts: string[]): Promise<number[][]> {
  const extractor = await getEmbedder()
  const results = await Promise.all(
    texts.map(t => extractor(t, { pooling: 'mean', normalize: true }))
  )
  return results.map(r => Array.from(r.data as Float32Array))
}

export const EMBEDDING_CONFIG = {
  modelName: MODEL_NAME,
  dim: EMBEDDING_DIM,
}
