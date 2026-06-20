import prisma from '../config/database'
import { TripContentSchema } from '../types/agent'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import { extractJson } from '../utils/jsonExtractor'

const MAX_OPTIMIZE_RETRIES = 2

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export async function optimizeTrip(tripId: number, instruction: string, userId: number | null = null) {
  const trip = await prisma.trip.findFirst({ where: { id: tripId } })
  if (!trip) throw new Error('行程不存在')

  const content = trip.content as Record<string, unknown>
  const userPrompt = instruction
    ? `请优化以下行程，根据要求调整：${instruction}\n\n原始行程（JSON）：\n${JSON.stringify(content, null, 2)}\n\n请以 JSON 格式输出优化后的版本，保持结构和预算、天数不变。`
    : `请优化以下行程，在预算${trip.budget}元、${trip.days}天的框架下给出更好的安排。\n\n原始行程（JSON）：\n${JSON.stringify(content, null, 2)}\n\n请以 JSON 格式输出优化后的版本。`

  const systemMsg = new SystemMessage(
    '你是一个专业的旅行规划优化专家。根据用户的要求优化行程，保持 JSON 输出格式不变。' +
      '严格遵循字段名/类型/数字不加引号，禁止 markdown 代码块或前后缀文字。',
  )

  let parsed: ReturnType<typeof TripContentSchema.parse> | null = null
  let lastError: unknown

  for (let attempt = 0; attempt <= MAX_OPTIMIZE_RETRIES; attempt++) {
    const humanMsg = attempt === 0
      ? new HumanMessage(userPrompt)
      : new HumanMessage(
          `上一次的输出解析失败：${lastError instanceof Error ? lastError.message : String(lastError)}\n` +
          `请严格按照 JSON 规范重新输出。\n\n原任务：\n${userPrompt}`,
        )

    const llm = createLLM({ streaming: false, temperature: 0.5 })
    const response = await llm.invoke([systemMsg, humanMsg])
    const rawContent = response.content as string

    try {
      const candidate = extractJson(rawContent)
      parsed = TripContentSchema.parse(candidate)
      break
    } catch (e) {
      lastError = e
      console.warn(`[Optimize] 第 ${attempt + 1} 次解析失败:`, e instanceof Error ? e.message : e)
      if (attempt < MAX_OPTIMIZE_RETRIES) {
        await sleep(800 * (attempt + 1))
      }
    }
  }

  if (!parsed) {
    const msg = lastError instanceof Error ? lastError.message : '未知错误'
    throw new Error(`行程优化输出多次解析失败：${msg}`)
  }

  const created = await prisma.trip.create({
    data: {
      userId,
      fromCity: trip.fromCity,
      city: parsed.city,
      days: parsed.days,
      budget: trip.budget,
      content: parsed as any,
      status: 'completed',
      parentTripId: tripId,
    },
  })

  return {
    success: true,
    data: {
      id: created.id,
      city: parsed.city,
      days: parsed.days,
      totalBudget: parsed.totalBudget,
      dailyItinerary: parsed.dailyItinerary,
      budgetBreakdown: parsed.budgetBreakdown,
      tips: parsed.tips,
      warnings: parsed.warnings,
    },
  }
}
