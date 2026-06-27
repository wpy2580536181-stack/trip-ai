// trip-server/src/services/agent/state.ts
import { Annotation } from '@langchain/langgraph'
import type { BaseMessage } from '@langchain/core/messages'
import type { TripContent, TokenUsage } from '../../types/agent'
import type { ResearchBundle } from './types'

export const PlannerState = Annotation.Root({
  // 输入
  userId: Annotation<number>,
  message: Annotation<string>,
  city: Annotation<string>,
  budget: Annotation<number | undefined>,
  days: Annotation<number | undefined>,
  departureCity: Annotation<string | undefined>,
  userPreferences: Annotation<Record<string, any> | null | undefined>,
  conversationHistory: Annotation<BaseMessage[]>,
  // research 产出
  researchBundle: Annotation<ResearchBundle>,
  // planner 产出
  rawOutput: Annotation<string | undefined>,
  parsed: Annotation<TripContent | undefined>,
  // 元数据
  usage: Annotation<TokenUsage>,
  route: Annotation<'planning' | 'general' | undefined>,
  errors: Annotation<string[]>,
})