package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * Review 结果 DTO
 */
public record ReviewResult(
    boolean passed,
    List<String> issues,
    Map<String, Object> budgetBreakdown
) {
    public static ReviewResult passed() {
        return new ReviewResult(true, List.of(), Map.of());
    }

    public static ReviewResult failed(List<String> issues) {
        return new ReviewResult(false, issues, Map.of());
    }

    public static ReviewResult failed(String issue) {
        return new ReviewResult(false, List.of(issue), Map.of());
    }
}
