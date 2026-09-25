package com.trip.backend.service.alert;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 告警检测器（对应 Python alert_detector.py）。
 *
 * <p>纯逻辑：给定窗口内 up（rating=1）/ down（rating=-1）反馈数，算满意率。
 * 触发条件：total &gt;= minFeedbacks 且 rate &lt; threshold。DB 查询由调用方完成。
 */
@Component
public class AlertDetector {

    /** 默认阈值：满意率 0.5，最少样本 5 条（对齐 backlog J-E1 判定）。 */
    public static final double DEFAULT_THRESHOLD = 0.5;
    public static final int DEFAULT_MIN_FEEDBACKS = 5;
    public static final int DEFAULT_WINDOW_MINUTES = 60;

    public AlertCheckResult check(int up, int down, List<Map<String, Object>> recentDownComments) {
        return check(up, down, recentDownComments, DEFAULT_THRESHOLD, DEFAULT_MIN_FEEDBACKS, DEFAULT_WINDOW_MINUTES);
    }

    public AlertCheckResult check(int up, int down, List<Map<String, Object>> recentDownComments,
                                  double threshold, int minFeedbacks, int windowMinutes) {
        int total = up + down;
        double rate = total > 0 ? (double) up / total : 0.0;
        boolean shouldAlert = total >= minFeedbacks && rate < threshold;

        String reason;
        if (shouldAlert) {
            reason = String.format("过去 %d 分钟 %d 条反馈，满意率 %.1f%% < %.0f%%",
                    windowMinutes, total, rate * 100, threshold * 100);
        } else if (total < minFeedbacks) {
            reason = String.format("样本不足：%d/%d 反馈", total, minFeedbacks);
        } else {
            reason = String.format("正常：%d 条反馈，满意率 %.1f%%", total, rate * 100);
        }

        Map<String, Object> stats = new HashMap<>();
        stats.put("feedbackCount", total);
        stats.put("upCount", up);
        stats.put("downCount", down);
        stats.put("satisfactionRate", rate);
        stats.put("recentDownComments", recentDownComments == null ? List.of() : new ArrayList<>(recentDownComments));

        return new AlertCheckResult(shouldAlert, reason, stats, threshold, minFeedbacks);
    }
}
