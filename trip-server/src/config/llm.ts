import { ChatOpenAI } from '@langchain/openai'

export type ModelProvider = 'KIMI' | 'DEEPSEEK'

export interface LLMConfig {
  apiKey: string
  baseURL: string
  model: string
}

export function loadLLMConfigForProvider(provider: string): LLMConfig | null {
  const upper = provider.toUpperCase()
  const apiKey = process.env[`${upper}_API_KEY`]
  const baseURL = process.env[`${upper}_BASE_URL`]
  const model = process.env[`${upper}_MODEL`]
  if (!apiKey || !baseURL || !model) return null
  return { apiKey, baseURL, model }
}

export function loadLLMConfig(): LLMConfig {
  const provider = (process.env.MODEL_PROVIDER as ModelProvider) || 'DEEPSEEK'
  const cfg = loadLLMConfigForProvider(provider)
  if (!cfg) {
    throw new Error(`${provider} 配置缺失`)
  }
  return cfg
}

export function loadFallbackLLMConfig(): LLMConfig | null {
  const fallback = process.env.MODEL_PROVIDER_FALLBACK
  if (!fallback) return null
  return loadLLMConfigForProvider(fallback)
}

export function createLLMFromConfig(cfg: LLMConfig, opts: { streaming?: boolean; temperature?: number } = {}): ChatOpenAI {
  const { streaming = true, temperature = 0.7 } = opts
  return new ChatOpenAI({
    configuration: { apiKey: cfg.apiKey, baseURL: cfg.baseURL },
    model: cfg.model,
    temperature,
    streaming,
  })
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
