package com.trip.backend.service.agent.dto;

/**
 * 计划请求（G4 简化版）
 */
public record PlanRequest(
    String city,
    Integer days,
    Integer budget,
    String message
) {
    /** 兼容：无用户原始 message。 */
    public PlanRequest(String city, Integer days, Integer budget) {
        this(city, days, budget, null);
    }
}
