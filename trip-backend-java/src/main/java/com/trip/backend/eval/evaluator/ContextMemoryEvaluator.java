package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * ContextMemoryEvaluator: 上下文记忆检查
 */
public class ContextMemoryEvaluator extends BaseEvaluator {

    public ContextMemoryEvaluator() {
        super("context_memory");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        return true; // 占位符
    }

    @Override
    public String getReason() {
        return "上下文记忆检查通过（占位符）";
    }
}
