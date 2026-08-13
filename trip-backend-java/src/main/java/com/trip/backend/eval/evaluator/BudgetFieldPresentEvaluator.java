package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * BudgetFieldPresentEvaluator: 预算字段检查
 */
public class BudgetFieldPresentEvaluator extends BaseEvaluator {

    public BudgetFieldPresentEvaluator() {
        super("budget_field_present");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        return text != null && (
            text.contains("元") ||
            text.contains("价格") ||
            text.contains("费用") ||
            text.contains("预算") ||
            text.contains("¥")
        );
    }

    @Override
    public String getReason() {
        return "包含预算信息";
    }
}
