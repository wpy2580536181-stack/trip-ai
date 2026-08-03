package com.trip.backend.service.agent.dto;

import java.util.Map;

/**
 * 计划结果（G4 简化版）
 */
public record PlanResult(
    Map<String, Object> plan
) {
    public static PlanResult of(Map<String, Object> plan) {
        return new PlanResult(plan);
    }

    public static PlanResult error(String error) {
        return new PlanResult(Map.of("error", error));
    }
}
