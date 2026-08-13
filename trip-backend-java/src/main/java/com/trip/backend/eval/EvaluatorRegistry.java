package com.trip.backend.eval;

import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * EvaluatorRegistry: 管理所有 Evaluator
 */
public class EvaluatorRegistry {

    /**
     * 列出所有 evaluator
     */
    public static List<String> listEvaluators() {
        return List.of(
            "schema_check",
            "poi_city_match",
            "keyword_coverage",
            "tool_call_audit",
            "pace_consistency",
            "pet_constraint_check",
            "dietary_constraint_check",
            "weather_adaptation_check",
            "budget_field_present",
            "kid_friendly_check",
            "destination_override",
            "context_memory",
            "no_forced_itinerary"
        );
    }

    /**
     * 执行单个 evaluator（占位符）
     */
    public static Map<String, Object> evaluate(String name, Map<String, Object> fixture, Map<String, Object> agentOutput) {
        return Map.of(
            "name", name,
            "passed", false,
            "reason", "未实现: " + name
        );
    }
}
