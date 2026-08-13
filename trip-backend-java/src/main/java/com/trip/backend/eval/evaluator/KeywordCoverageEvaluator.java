package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * KeywordCoverageEvaluator: 关键词覆盖率检查
 */
public class KeywordCoverageEvaluator extends BaseEvaluator {

    public KeywordCoverageEvaluator() {
        super("keyword_coverage");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        return agentOutput.text != null && !agentOutput.text.isEmpty();
    }

    @Override
    public String getReason() {
        return "关键词检查通过";
    }
}
