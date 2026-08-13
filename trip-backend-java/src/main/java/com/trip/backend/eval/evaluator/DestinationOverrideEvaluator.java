package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * DestinationOverrideEvaluator: 目的地覆盖检查
 */
public class DestinationOverrideEvaluator extends BaseEvaluator {

    public DestinationOverrideEvaluator() {
        super("destination_override");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        return true; // 占位符
    }

    @Override
    public String getReason() {
        return "目的地覆盖检查通过（占位符）";
    }
}
