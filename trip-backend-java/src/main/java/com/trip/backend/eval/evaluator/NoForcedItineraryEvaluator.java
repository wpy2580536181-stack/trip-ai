package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * NoForcedItineraryEvaluator: 检查是否被强制生成行程
 */
public class NoForcedItineraryEvaluator extends BaseEvaluator {

    public NoForcedItineraryEvaluator() {
        super("no_forced_itinerary");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        if (text == null) return false;

        boolean hasRefused = text.contains("无法提供") ||
                            text.contains("无法为您") ||
                            text.contains("抱歉") ||
                            text.contains("我不是") ||
                            text.contains("无法回答");

        return hasRefused;
    }

    @Override
    public String getReason() {
        return "正确拒答（非旅行问题）";
    }
}
