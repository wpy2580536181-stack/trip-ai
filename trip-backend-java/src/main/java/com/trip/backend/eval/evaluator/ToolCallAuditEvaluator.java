package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * ToolCallAuditEvaluator: 工具调用审计
 */
public class ToolCallAuditEvaluator extends BaseEvaluator {

    public ToolCallAuditEvaluator() {
        super("tool_call_audit");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        return true; // 占位符
    }

    @Override
    public String getReason() {
        return "工具调用审计通过（占位符）";
    }
}
