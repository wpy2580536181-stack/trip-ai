import { env, pipeline, FeatureExtractionPipeline } from '@xenova/transformers'
import { embeddingLog as log } from '../utils/logger'

const HF_MIRROR = process.env.HF_ENDPOINT || 'https://hf-mirror.com/'
env.remoteHost = HF_MIRROR
env.remotePathTemplate = '{model}/resolve/{revision}/'
log.info({ endpoint: HF_MIRROR }, '使用 HF endpoint')

const MODEL_NAME = 'Xenova/bge-small-zh-v1.5'
const EMBEDDING_DIM = 512

let extractorPromise: Promise<FeatureExtractionPipeline> | null = null

export function getEmbedder(): Promise<FeatureExtractionPipeline> {
  if (!extractorPromise) {
    log.info({ model: MODEL_NAME }, '正在加载模型')
    extractorPromise = pipeline('feature-extraction', MODEL_NAME) as Promise<FeatureExtractionPipeline>
    extractorPromise.then(() => {
      log.info('模型加载完成')
    }).catch((e) => {
      log.error({ err: e }, '模型加载失败')
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
