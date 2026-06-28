import type { RunnableConfig } from '@langchain/core/runnables'
import { retrieveKnowledgeTool } from '../tools/retrieveKnowledge'
import { searchHotelsTool } from '../tools/searchHotels'
import { calculateDistanceTool } from '../tools/calculateDistance'
import type { PlannerState } from '../state'
import type { PlannerConfig, ResearchBundle } from '../types'

const HOTEL_FALLBACK = '住宿信息暂时不可用，请基于通用旅行知识回答。'
const DISTANCE_FALLBACK = '距离计算暂时不可用。'

export async function researchNode(
  state: typeof PlannerState.State,
  config: RunnableConfig,
): Promise<Partial<typeof PlannerState.State>> {
  const { city, budget, days, departureCity, userPreferences } = state
  const { traceRecorder, onEvent, stepCounter } = config.configurable as PlannerConfig

  const interests = Array.isArray(userPreferences?.interests)
    ? (userPreferences!.interests as string[]).join('')
    : ''
  const hotelBudget = budget && days ? Math.round(budget / days / 1.5) : undefined

  type Task = { key: keyof ResearchBundle; name: string; fn: () => Promise<string> }
  const tasks: Task[] = [
    {
      key: 'attractions',
      name: 'retrieve_knowledge',
      fn: () => retrieveKnowledgeTool.invoke({
        query: `${city} 必去 景点 ${interests}`.trim(),
        city, category: 'attraction',
      }) as Promise<string>,
    },
    {
      key: 'food',
      name: 'retrieve_knowledge',
      fn: () => retrieveKnowledgeTool.invoke({
        query: `${city} 美食 推荐 ${interests}`.trim(),
        city, category: 'food',
      }) as Promise<string>,
    },
    {
      key: 'hotels',
      name: 'search_hotels',
      fn: () => searchHotelsTool.invoke({ city, budget: hotelBudget }) as Promise<string>,
    },
  ]
  if (departureCity) {
    tasks.push({
      key: 'distance',
      name: 'calculate_distance',
      fn: () => calculateDistanceTool.invoke({ from: departureCity, to: city }) as Promise<string>,
    })
  }

  // 记录每个 task 的起始时间，供 tool_end 计算 durationMs
  const startTimes: number[] = new Array(tasks.length).fill(0)

  // emit tool_start（逐个 emit，便于前端展示）
  for (const t of tasks) {
    startTimes[tasks.indexOf(t)] = Date.now()
    traceRecorder.add({ step: stepCounter.value++, type: 'tool_start', name: t.name })
    await onEvent({ type: 'tool_start', name: t.name })
  }

  const results = await Promise.allSettled(tasks.map(t => t.fn()))

  const bundle: ResearchBundle = {}
  const fallbacks: Record<keyof ResearchBundle, string> = {
    attractions: '景点信息暂时不可用，请基于通用旅行知识回答。',
    food: '美食信息暂时不可用，请基于通用旅行知识回答。',
    hotels: HOTEL_FALLBACK,
    distance: DISTANCE_FALLBACK,
  }

  tasks.forEach((t, i) => {
    const r = results[i]
    if (r.status === 'fulfilled') {
      bundle[t.key] = r.value
    } else {
      bundle[t.key] = fallbacks[t.key]
    }
    traceRecorder.add({ step: stepCounter.value++, type: 'tool_end', name: t.name, durationMs: Date.now() - startTimes[i] })
  })

  // emit tool_end
  for (const t of tasks) {
    await onEvent({ type: 'tool_end', name: t.name })
  }

  return { researchBundle: bundle }
}
