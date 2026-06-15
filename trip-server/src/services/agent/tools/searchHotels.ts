import { z } from 'zod'
import { DynamicStructuredTool } from '@langchain/community/tools/dynamic'
import { searchSpots } from '../../knowledgeService'
import { withResilience } from '../resilience'

const SearchHotelsInputSchema = z.object({
  city: z.string().describe('目标城市名'),
  budget: z.number().optional().describe('预算上限（元/晚）'),
  level: z.enum(['economy', 'comfort', 'luxury']).optional().describe('住宿档次'),
})

export const searchHotelsTool = withResilience(
  new DynamicStructuredTool({
    name: 'search_hotels',
    description: `查询目标城市的住宿信息。
当用户询问住宿、酒店、旅馆、民宿时使用。
输入：city（城市名）、budget（可选，预算上限）、level（可选，档次：economy/comfort/luxury）。
先在知识库中检索真实数据，若无结果则基于通用知识推荐。`,
    schema: SearchHotelsInputSchema,
    func: async (input: z.infer<typeof SearchHotelsInputSchema>) => {
      const results = await searchSpots({
        query: `${input.level ?? ''} ${input.city} 住宿酒店`.trim(),
        city: input.city,
        category: 'hotel',
        limit: 5,
      })
      if (!results || results === '(未找到相关景点)') {
        return `知识库中暂无 ${input.city} 的住宿数据${input.budget ? `，预算 ${input.budget} 元/晚` : ''}。请基于通用知识推荐。`
      }
      return results
    },
  }),
  {
    timeout: 10000,
    retries: 1,
    fallback: '住宿信息暂时不可用，请基于通用旅行知识回答。',
  },
)
