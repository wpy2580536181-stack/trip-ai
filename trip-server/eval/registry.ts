/**
 * Evaluator 注册表
 * 新增 evaluator 时：
 * 1) 在对应 evaluators/*.ts 里实现
 * 2) 在这里注册
 */

import type { EvaluatorFn } from './types'
import {
  schemaCheck,
  poiCityMatch,
  keywordCoverage,
  toolCallAudit,
  paceConsistency,
} from './evaluators/general'
import {
  petConstraintCheck,
  dietaryConstraintCheck,
  weatherAdaptationCheck,
  budgetFieldPresent,
  kidFriendlyCheck,
} from './evaluators/domain'
import {
  destinationOverride,
  contextMemory,
  noForcedItinerary,
} from './evaluators/multi-turn'

export const EVALUATORS: Record<string, EvaluatorFn> = {
  // 通用
  schema_check: schemaCheck,
  poi_city_match: poiCityMatch,
  keyword_coverage: keywordCoverage,
  tool_call_audit: toolCallAudit,
  pace_consistency: paceConsistency,

  // 领域
  pet_constraint_check: petConstraintCheck,
  dietary_constraint_check: dietaryConstraintCheck,
  weather_adaptation_check: weatherAdaptationCheck,
  budget_field_present: budgetFieldPresent,
  kid_friendly_check: kidFriendlyCheck,

  // 多轮 + 反例
  destination_override: destinationOverride,
  context_memory: contextMemory,
  no_forced_itinerary: noForcedItinerary,
}

export function getEvaluator(name: string): EvaluatorFn | undefined {
  return EVALUATORS[name]
}

export function listEvaluators(): string[] {
  return Object.keys(EVALUATORS)
}
