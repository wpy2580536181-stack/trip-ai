package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

/**
 * PoiCityMatchEvaluator: POI 城市匹配
 */
public class PoiCityMatchEvaluator extends BaseEvaluator {

    public PoiCityMatchEvaluator() {
        super("poi_city_match");
    }

    @Override
    public boolean evaluate(AgentOutput agentOutput) {
        return true; // 占位符
    }

    @Override
    public String getReason() {
        return "POI 匹配通过（占位符）";
    }
}
