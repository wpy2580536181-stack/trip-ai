package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * Planner 输入 DTO
 */
public record PlannerInput(
    ResearchBundle research,
    String feedback,
    boolean isPartial,
    List<Integer> targetDays
) {
    public static PlannerInput full(ResearchBundle research) {
        return new PlannerInput(research, null, false, List.of());
    }

    public static PlannerInput withFeedback(ResearchBundle research, String feedback) {
        return new PlannerInput(research, feedback, false, List.of());
    }

    public static PlannerInput partial(ResearchBundle research, List<Integer> targetDays) {
        return new PlannerInput(research, null, true, targetDays);
    }
}
