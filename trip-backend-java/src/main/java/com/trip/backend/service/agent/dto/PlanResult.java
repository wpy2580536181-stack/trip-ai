package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * 计划结果 DTO
 */
public record PlanResult(
    Map<String, Object> plan,
    ReviewResult review,
    TokenUsage usage,
    List<VariantResult> variants
) {
    public static PlanResult of(Map<String, Object> plan, ReviewResult review, TokenUsage usage) {
        return new PlanResult(plan, review, usage, List.of());
    }

    public static PlanResult of(Map<String, Object> plan, ReviewResult review, TokenUsage usage, List<VariantResult> variants) {
        return new PlanResult(plan, review, usage, variants);
    }
}
