import { z } from 'zod'
import { DynamicStructuredTool } from '@langchain/community/tools/dynamic'
import { searchSpots } from '../../knowledgeService'
import { withResilience } from '../resilience'

const RetrieveKnowledgeInputSchema = z.object({
  query: z.string().describe('搜索关键词，描述你想了解的景点主题'),
  city: z.string().describe('目标城市名'),
  category: z.enum(['attraction', 'food', 'hotel', 'transport']).optional()
    .describe('景点类型：景点/美食/住宿/交通'),
})

/**
 * RAG 工具：从知识库检索景点信息
 * Agent 自主决定何时调用
 */
export const retrieveKnowledgeTool = withResilience(
  new DynamicStructuredTool({
    name: 'retrieve_knowledge',
    description: `从旅行知识库检索景点、美食、住宿、交通等真实信息。
当用户询问某个城市具体的景点推荐、美食、交通、住宿时，必须调用此工具获取真实数据。
输入：query（搜索关键词）、city（城市名）、category（可选，景点类型）。`,
    schema: RetrieveKnowledgeInputSchema,
    func: async (input: z.infer<typeof RetrieveKnowledgeInputSchema>) => {
      const results = await searchSpots({
        query: input.query,
        city: input.city,
        category: input.category,
        limit: 5,
      })
      if (!results) {
        return `知识库中没有找到 ${input.city} 的相关信息。`
      }
      return results
    },
  }),
  {
    timeout: 8000,
    retries: 1,
    fallback: '知识库暂时不可用，请基于通用旅行知识回答。',
  }
)
