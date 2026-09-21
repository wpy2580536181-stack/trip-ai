package com.trip.backend.service.agent;

import java.util.List;
import java.util.Map;

/**
 * Review 阶段结果（对应 Python schemas.ReviewResult）。
 */
public record ReviewResult(
    boolean passed,
    List<String> issues,
    String feedback,
    Map<String, Object> codeChecks
) {
    public static ReviewResult passed(Map<String, Object> checks) {
        return new ReviewResult(true, List.of(), "", checks);
    }

    public static ReviewResult fail(String issue, String feedback, Map<String, Object> checks) {
        return new ReviewResult(false, List.of(issue), feedback, checks);
    }
}
