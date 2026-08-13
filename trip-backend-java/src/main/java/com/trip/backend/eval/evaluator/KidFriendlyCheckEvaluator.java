package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * KidFriendlyCheckEvaluator: 儿童友好检查
 */
public class KidFriendlyCheckEvaluator extends BaseEvaluator {

    public KidFriendlyCheckEvaluator() {
        super("kid_friendly_check");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        return text != null && (
            text.contains("儿童") ||
            text.contains("孩子") ||
            text.contains("亲子") ||
            text.contains("kid") ||
            text.contains("child")
        );
    }

    @Override
    public String getReason() {
        return "包含儿童友好信息";
    }
}
