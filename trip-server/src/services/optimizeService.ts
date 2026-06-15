import prisma from '../config/database'
import { TripContentSchema } from '../types/agent'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import { extractJson } from '../utils/jsonExtractor'
import { z } from 'zod'

const OptimizeInputSchema = z.object({
  city: z.string(),
  days: z.number(),
  totalBudget: z.number(),
  dailyItinerary: z.array(z.any()),
  budgetBreakdown: z.any(),
  tips: z.array(z.string()).optional(),
  warnings: z.array(z.string()).optional(),
})

export async function optimizeTrip(tripId: number, instruction: string, userId: number | null = null) {
  const trip = await prisma.trip.findFirst({ where: { id: tripId } })
  if (!trip) throw new Error('行程不存在')

  const content = trip.content as Record<string, unknown>
  const prompt = instruction
    ? `请优化以下行程，根据要求调整：${instruction}\n\n原始行程（JSON）：\n${JSON.stringify(content, null, 2)}\n\n请以 JSON 格式输出优化后的版本，保持结构和预算、天数不变。`
    : `请优化以下行程，在预算${trip.budget}元、${trip.days}天的框架下给出更好的安排。\n\n原始行程（JSON）：\n${JSON.stringify(content, null, 2)}\n\n请以 JSON 格式输出优化后的版本。`

  const systemMsg = new SystemMessage(
    '你是一个专业的旅行规划优化专家。根据用户的要求优化行程，保持 JSON 输出格式不变。',
  )
  const humanMsg = new HumanMessage(prompt)

  const llm = createLLM({ streaming: false, temperature: 0.5 })
  const response = await llm.invoke([systemMsg, humanMsg])
  const rawContent = response.content as string
  const parsed = OptimizeInputSchema.parse(extractJson(rawContent))

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
