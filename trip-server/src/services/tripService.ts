import { ChatOpenAI } from '@langchain/openai'
import { HumanMessage , SystemMessage } from '@langchain/core/messages'


class TripService {
  private llm: ChatOpenAI | null = null

  constructor() {
    this.initLLM()
  }
  //初始化大模型
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
    const messages = this.getTripPrompt(city, budget, days)
    // 调用大模型
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
  getTripPrompt(city: string, budget: number, days: number){
    return [
      new HumanMessage(`你是一个专业的旅游规划师，擅长根据用户的需求生成详细的旅行行程。
 
请根据以下信息为用户生成一份详细的旅游规划：
- 目的地城市：${city}
- 预算：${budget}元
- 旅行天数：${days}天
 
要求：
1. 每天的行程安排（上午、下午、晚上）
2. 每个景点的详细介绍
3. 交通建议
4. 预算分配明细
5. 注意事项
 
请以JSON格式输出，结构如下：
{
  "success": true,
  "city": "城市名",
  "days": 天数,
  "totalBudget": 总预算,
  "dailyItinerary": [
    {
      "day": 1,
      "date": "第1天",
      "morning": {
        "spot": "景点名称",
        "duration": "游览时长",
        "ticket": "门票价格",
        "transportation": "交通方式",
        "description": "景点介绍"
      },
      "afternoon": {
        "spot": "景点名称",
        "duration": "游览时长",
        "ticket": "门票价格",
        "transportation": "交通方式",
        "description": "景点介绍"
      },
      "evening": {
        "spot": "活动名称",
        "duration": "活动时长",
        "ticket": "费用",
        "transportation": "交通方式",
        "description": "活动介绍"
      }
    }
  ],
  "budgetBreakdown": {
    "accommodation": 住宿费用,
    "food": 餐饮费用,
    "transportation": 交通费用,
    "tickets": 门票费用,
    "other": 其他费用
  },
  "tips": ["提示1", "提示2", "提示3"],
  "warnings": ["注意事项1", "注意事项2"]
}
 
请确保JSON格式正确，可以被解析。`),
    ]
  }
  //流式对话
  async chat(message:string,streamCallback:any){
    // 构建消息
    const messages = [
      new SystemMessage('你是一个专业的旅游规划师，擅长根据用户的需求生成详细的旅行行程。'),
      new HumanMessage(message)
    ]
    if (!this.llm) {
      throw new Error('LLM未初始化')
    }
    try{
      const stream = await this.llm.stream(messages)

    let fullResponse = ''
    // 处理流式响应
    for await (const chunk of stream) {
      const content = chunk.content as string
      if (!content || content.trim() === '') {
        continue
      }
      fullResponse += content
      if (streamCallback) {
        streamCallback(content)
      }
    }
    return{
      success: true,
      reply: fullResponse,
    }
    }catch(error){
      return{
        success: false,
        error: '缺少参数或参数错误'
      }
    }

  }
}
export default  new TripService()
