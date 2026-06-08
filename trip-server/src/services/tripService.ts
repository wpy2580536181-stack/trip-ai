import { ChatOpenAI } from '@langchain/openai'
import { HumanMessage , SystemMessage } from '@langchain/core/messages'
import { buildTripPrompt } from '../prompts/trip.prompt'

class TripService {
  private llm: ChatOpenAI | null = null

  constructor() {
    this.initLLM()
  }

  initLLM() {
    const modelProvider = process.env.MODEL_PROVIDER
    let apikey,baseURL,model;
    if(modelProvider === 'KIMI'){
      apikey = process.env.KIMI_API_KEY
      baseURL = process.env.KIMI_BASE_URL
      model = process.env.KIMI_MODEL
    }else if(modelProvider === 'DEEPSEEK'){
      apikey = process.env.DEEPSEEK_API_KEY
      baseURL = process.env.DEEPSEEK_BASE_URL
      model = process.env.DEEPSEEK_MODEL
    }
    this.llm = new ChatOpenAI({
        configuration: {
          apiKey: apikey,
          baseURL: baseURL,
        },
        model,
        temperature: 0.7,
        streaming: true,
    })
  }

  async recommend(city: string, budget: number, days: number) {
    if(budget<50||days<1||days>30){
      throw new Error('预算过低或天数不符合要求')
    }
    const messages = [new HumanMessage(buildTripPrompt(city, budget, days))]
    if (!this.llm) {
      throw new Error('LLM未初始化')
    }
    try {
      const response = await this.llm.invoke(messages)
      const rawContent = response.content as string
      const jsonMatch = rawContent.match(/\{[\s\S]*\}/)
      if (!jsonMatch) {
        throw new Error('大模型返回格式异常，无法解析JSON')
      }
      const parsed = JSON.parse(jsonMatch[0])
      return {
        success: true,
        data: {
          city: parsed.city,
          days: parsed.days,
          totalBudget: parsed.totalBudget,
          dailyItinerary: parsed.dailyItinerary,
          budgetBreakdown: parsed.budgetBreakdown,
          tips: parsed.tips,
          warnings: parsed.warnings,
        },
      }
    } catch (error) {
      console.error('大模型调用失败:', error)
      throw new Error('大模型调用失败，请稍后重试')
    }
  }

  async chat(message:string, streamCallback: (chunk: string) => void) {
    const messages = [
      new SystemMessage('你是一个专业的旅游规划师，擅长根据用户的需求生成详细的旅行行程。'),
      new HumanMessage(message)
    ]
    if (!this.llm) {
      throw new Error('LLM未初始化')
    }
    try {
      const stream = await this.llm.stream(messages)
      let fullResponse = ''
      for await (const chunk of stream) {
        const content = chunk.content as string
        if (!content || content.trim() === '') {
          continue
        }
        fullResponse += content
        streamCallback(content)
      }
      return {
        success: true,
        reply: fullResponse,
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '未知错误'
      return {
        success: false,
        error: `AI 响应异常：${message}`,
      }
    }
  }
}
export default new TripService()
