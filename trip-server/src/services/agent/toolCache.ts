import { DynamicStructuredTool } from '@langchain/community/tools/dynamic'
import type { ToolCache } from '../llmGuard/toolCache'

/**
 * 给 tool 加缓存层。**必须套在 withResilience 外面**：
 *   withToolCache → withResilience → 原始 tool
 *
 * 顺序原因：
 * - 缓存命中时直接返回，跳过整个 withResilience（包括重试和 fallback）
 * - 缓存未命中时走 withResilience 正常流程（重试 + fallback）
 * - 反过来套（withResilience 包 withToolCache）会导致缓存层超时也走 fallback 路径
 */
export function withToolCache(
  tool: DynamicStructuredTool,
  config: { cache: ToolCache; toolName: string },
): DynamicStructuredTool {
  return new DynamicStructuredTool({
    name: tool.name,
    description: tool.description,
    schema: tool.schema,
    func: async (input) => {
      const { result } = await config.cache.getOrCompute(
        config.toolName,
        input as Record<string, unknown>,
        () => tool.call(input) as Promise<string>,
      )
      return result
    },
  })
}
