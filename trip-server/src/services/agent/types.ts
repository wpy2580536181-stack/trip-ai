// trip-server/src/services/agent/types.ts
import type { TraceRecorder } from './traceRecorder'
import type { AgentStreamEvent, TokenUsage } from '../../types/agent'

/** research 节点产出的情报包，planner 节点消费 */
export interface ResearchBundle {
  attractions?: string
  food?: string
  hotels?: string
  weather?: string
  distance?: string
}

/** LangGraph config.configurable 注入的非可变依赖 */
export interface PlannerConfig {
  traceRecorder: TraceRecorder
  onEvent: (event: AgentStreamEvent) => Promise<void>
  signal?: AbortSignal
  stepCounter: { value: number }
}

/** 空的 TokenUsage 工厂 */
export function emptyUsage(): TokenUsage {
  return { prompt: 0, completion: 0, total: 0, cached: 0 }
}