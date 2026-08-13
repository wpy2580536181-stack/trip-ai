package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * WeatherAdaptationCheckEvaluator: 天气适应性检查
 */
public class WeatherAdaptationCheckEvaluator extends BaseEvaluator {

    public WeatherAdaptationCheckEvaluator() {
        super("weather_adaptation_check");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        String text = agentOutput.text;
        return text != null && (
            text.contains("天气") ||
            text.contains("雨天") ||
            text.contains("晴天") ||
            text.contains("weather") ||
            text.contains("室内")
        );
    }

    @Override
    public String getReason() {
        return "考虑天气因素";
    }
}
