package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * PaceConsistencyEvaluator: 行程节奏检查
 */
public class PaceConsistencyEvaluator extends BaseEvaluator {

    public PaceConsistencyEvaluator() {
        super("pace_consistency");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        return text != null && (
            text.contains("天") ||
            text.contains("上午") ||
            text.contains("下午") ||
            text.contains("晚上")
        );
    }

    @Override
    public String getReason() {
        return "行程节奏合理";
    }
}
