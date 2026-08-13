package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * DietaryConstraintCheckEvaluator: 饮食限制检查
 */
public class DietaryConstraintCheckEvaluator extends BaseEvaluator {

    public DietaryConstraintCheckEvaluator() {
        super("dietary_constraint_check");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        return text != null && (
            text.contains("清真") ||
            text.contains("素食") ||
            text.contains("halal") ||
            text.contains("vegetarian")
        );
    }

    @Override
    public String getReason() {
        return "符合饮食限制";
    }
}
