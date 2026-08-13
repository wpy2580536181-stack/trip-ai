package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * PetConstraintCheckEvaluator: 宠物限制检查
 */
public class PetConstraintCheckEvaluator extends BaseEvaluator {

    public PetConstraintCheckEvaluator() {
        super("pet_constraint_check");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        return text != null && (
            text.contains("宠物") ||
            text.contains("pet") ||
            text.contains("狗") ||
            text.contains("猫")
        );
    }

    @Override
    public String getReason() {
        return "包含宠物信息";
    }
}
