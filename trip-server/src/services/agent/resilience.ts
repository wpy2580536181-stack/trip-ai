import { DynamicStructuredTool } from '@langchain/community/tools/dynamic'

export interface ResilienceConfig {
  timeout?: number
  retries?: number
  fallback?: string
  toolName?: string
}

const DEFAULT_TIMEOUT = 5000
const DEFAULT_RETRIES = 2

/**
 * 为工具增加超时、重试、降级
 */
export function withResilience<T extends DynamicStructuredTool>(tool: T, config: ResilienceConfig = {}): T {
  const timeout = config.timeout ?? DEFAULT_TIMEOUT
  const retries = config.retries ?? DEFAULT_RETRIES
  const fallback = config.fallback ?? `工具 ${config.toolName ?? tool.name} 暂时无法使用，请稍后再试`
  const toolName = config.toolName ?? tool.name

  const wrapped = new DynamicStructuredTool({
    name: tool.name,
    description: tool.description,
    schema: tool.schema,
    func: async (input) => {
      let lastError: unknown
      for (let attempt = 0; attempt <= retries; attempt++) {
        let timer: ReturnType<typeof setTimeout> | undefined
        try {
          const result = await Promise.race([
            tool.call(input),
            new Promise<never>((_, reject) => {
              timer = setTimeout(() => reject(new Error('Tool timeout')), timeout)
            }),
          ])
          return result
        } catch (e) {
          lastError = e
          const errMsg = e instanceof Error ? e.message : String(e)
          console.warn(`[Resilience] 工具 ${toolName} 第 ${attempt + 1} 次失败: ${errMsg}`)
          if (attempt < retries) {
            await sleep(Math.min(1000 * (attempt + 1), 3000))
          }
        } finally {
          if (timer) clearTimeout(timer)
        }
      }
      console.error(`[Resilience] 工具 ${toolName} 全部重试失败，降级返回: ${lastError instanceof Error ? lastError.message : lastError}`)
      return fallback
    },
  }) as T

  return wrapped
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
