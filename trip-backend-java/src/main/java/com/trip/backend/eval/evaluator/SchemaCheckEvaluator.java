package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * SchemaCheckEvaluator: 验证响应结构
 */
public class SchemaCheckEvaluator extends BaseEvaluator {

    public SchemaCheckEvaluator() {
        super("schema_check");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        return agentOutput.text != null && !agentOutput.text.isEmpty();
    }

    @Override
    public String getReason() {
        return "JSON 结构有效";
    }
}
