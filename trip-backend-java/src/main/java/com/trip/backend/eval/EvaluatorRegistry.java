package com.trip.backend.eval;

import com.trip.backend.eval.evaluator.BaseEvaluator;
import com.trip.backend.eval.evaluator.BudgetFieldPresentEvaluator;
import com.trip.backend.eval.evaluator.ContextMemoryEvaluator;
import com.trip.backend.eval.evaluator.DestinationOverrideEvaluator;
import com.trip.backend.eval.evaluator.DietaryConstraintCheckEvaluator;
import com.trip.backend.eval.evaluator.KeywordCoverageEvaluator;
import com.trip.backend.eval.evaluator.KidFriendlyCheckEvaluator;
import com.trip.backend.eval.evaluator.NoForcedItineraryEvaluator;
import com.trip.backend.eval.evaluator.PaceConsistencyEvaluator;
import com.trip.backend.eval.evaluator.PetConstraintCheckEvaluator;
import com.trip.backend.eval.evaluator.PoiCityMatchEvaluator;
import com.trip.backend.eval.evaluator.SchemaCheckEvaluator;
import com.trip.backend.eval.evaluator.ToolCallAuditEvaluator;
import com.trip.backend.eval.evaluator.WeatherAdaptationCheckEvaluator;
import com.trip.backend.eval.types.AgentOutput;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * EvaluatorRegistry: 13 个 evaluator
 */
public class EvaluatorRegistry {

    private static final Map<String, BaseEvaluator> EVALUATORS = new HashMap<>();

    static {
        EVALUATORS.put("schema_check", new SchemaCheckEvaluator());
        EVALUATORS.put("poi_city_match", new PoiCityMatchEvaluator());
        EVALUATORS.put("keyword_coverage", new KeywordCoverageEvaluator());
        EVALUATORS.put("tool_call_audit", new ToolCallAuditEvaluator());
        EVALUATORS.put("pace_consistency", new PaceConsistencyEvaluator());
        EVALUATORS.put("pet_constraint_check", new PetConstraintCheckEvaluator());
        EVALUATORS.put("dietary_constraint_check", new DietaryConstraintCheckEvaluator());
        EVALUATORS.put("weather_adaptation_check", new WeatherAdaptationCheckEvaluator());
        EVALUATORS.put("budget_field_present", new BudgetFieldPresentEvaluator());
        EVALUATORS.put("kid_friendly_check", new KidFriendlyCheckEvaluator());
        EVALUATORS.put("destination_override", new DestinationOverrideEvaluator());
        EVALUATORS.put("context_memory", new ContextMemoryEvaluator());
        EVALUATORS.put("no_forced_itinerary", new NoForcedItineraryEvaluator());
    }

    public static List<String> listEvaluators() {
        return EVALUATORS.keySet().stream().toList();
    }

    public static BaseEvaluator getEvaluator(String name) {
        return EVALUATORS.get(name);
    }

    public static Map<String, Object> evaluate(String name, Map<String, Object> fixture, Map<String, Object> agentOutput) {
        BaseEvaluator evaluator = EVALUATORS.get(name);
        if (evaluator == null) {
            Map<String, Object> result = new java.util.HashMap<>();
            result.put("name", name);
            result.put("passed", false);
            result.put("reason", "未找到");
            return result;
        }

        boolean passed = evaluator.evaluate(new AgentOutput());
        Map<String, Object> result = new java.util.HashMap<>();
        result.put("name", name);
        result.put("passed", passed);
        result.put("reason", passed ? "通过" : "失败");
        return result;
    }
}
