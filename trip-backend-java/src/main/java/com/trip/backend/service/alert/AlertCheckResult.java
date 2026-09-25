package com.trip.backend.service.alert;

import java.util.List;
import java.util.Map;

/**
 * 告警检测结果（对应 Python alert_detector.AlertCheckResult）。
 */
public record AlertCheckResult(
        boolean shouldAlert,
        String reason,
        Map<String, Object> stats,
        double threshold,
        int minFeedbacks) {

    /** 最近差评条目（comment/tags/createdAt）。 */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> recentDownComments() {
        Object v = stats.get("recentDownComments");
        if (v instanceof List<?> list) {
            return (List<Map<String, Object>>) list;
        }
        return List.of();
    }
}
