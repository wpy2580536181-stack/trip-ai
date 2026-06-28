import { DynamicTool } from '@langchain/core/tools'
import { logger } from '../../utils/logger'
import * as amapMcpClient from './amapMcpClient'
import * as amapGuards from './amapGuards'
import { AMAP_CONFIG } from '../../config/amap'

export async function loadAmapTools(): Promise<DynamicTool[]> {
  if (!AMAP_CONFIG.enabled) {
    logger.warn('[AmapMcp] Amap MCP disabled, skipping tool loading')
    return []
  }

  try {
    const mcpTools = await amapMcpClient.listTools()
    const tools = mcpTools.map(mcpTool => {
      return new DynamicTool({
        name: mcpTool.name,
        description: mcpTool.description + '（实时数据源，推荐用于天气、POI 搜索、路线规划）',
        tags: ['amap', 'realtime'],
        func: async (input: string) => {
          try {
            let args: Record<string, unknown>
            try {
              args = JSON.parse(input)
            } catch {
              args = { query: input }
            }
            const result = await amapGuards.call(mcpTool.name, args)
            return result
          } catch (err) {
            if (err instanceof Error) {
              const msg = err.message
              if (msg === 'AMAP_MCP_RATE_LIMITED') {
                return '【Amap MCP 服务繁忙，请稍后重试或使用 RAG 知识库】'
              }
              if (msg === 'AMAP_MCP_CIRCUIT_OPEN') {
                return '【Amap MCP 暂时不可用，请使用 RAG 知识库获取信息】'
              }
            }
            logger.error({ err, toolName: mcpTool.name }, '[AmapMcp] tool call failed')
            return `【Amap ${mcpTool.name} 查询失败：${err}，请使用 RAG 知识库】`
          }
        },
      })
    })

    logger.info({ toolCount: tools.length, toolNames: tools.map(t => t.name) }, '[AmapMcp] tools loaded')
    return tools
  } catch (err) {
    logger.error({ err }, '[AmapMcp] failed to load tools from MCP server')
    return []
  }
}
