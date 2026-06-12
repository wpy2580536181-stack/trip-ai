import { ChatOpenAI } from '@langchain/openai'

export type ModelProvider = 'KIMI' | 'DEEPSEEK'

export interface LLMConfig {
  apiKey: string
  baseURL: string
  model: string
}

export function loadLLMConfig(): LLMConfig {
  const provider = (process.env.MODEL_PROVIDER as ModelProvider) || 'DEEPSEEK'
  if (provider === 'KIMI') {
    const apiKey = process.env.KIMI_API_KEY
    const baseURL = process.env.KIMI_BASE_URL
    const model = process.env.KIMI_MODEL
    if (!apiKey || !baseURL || !model) {
      throw new Error('KIMI 配置缺失：KIMI_API_KEY / KIMI_BASE_URL / KIMI_MODEL')
    }
    return { apiKey, baseURL, model }
  }
  const apiKey = process.env.DEEPSEEK_API_KEY
  const baseURL = process.env.DEEPSEEK_BASE_URL
  const model = process.env.DEEPSEEK_MODEL
  if (!apiKey || !baseURL || !model) {
    throw new Error('DEEPSEEK 配置缺失：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL')
  }
  return { apiKey, baseURL, model }
}

export function createLLM(opts: { streaming?: boolean; temperature?: number } = {}): ChatOpenAI {
  const { streaming = true, temperature = 0.7 } = opts
  const cfg = loadLLMConfig()
  return new ChatOpenAI({
    configuration: { apiKey: cfg.apiKey, baseURL: cfg.baseURL },
    model: cfg.model,
    temperature,
    streaming,
  })
}
