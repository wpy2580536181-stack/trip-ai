package com.trip.backend.service.agent;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Review 校验服务（对应 Python review.py）。
 *
 * 两层：
 *  - 第一层（确定性代码）：JSON 解析→天数→预算≤1.15×→budgetBreakdown 五键→候选池封闭世界
 *  - 第二层（LLM）：留 hook（llmReviewHook），默认不启用，避免依赖真 LLM
 */
@Service
public class ReviewService {

    private static final Logger log = LoggerFactory.getLogger(ReviewService.class);
    private static final double BUDGET_TOLERANCE = 1.15;
    private static final List<String> REQUIRED_BREAKDOWN_KEYS =
        List.of("accommodation", "food", "transportation", "tickets", "other");
    private static final List<String> PERIODS = List.of("morning", "afternoon", "evening");

    /** LLM 二审 hook（可选；返回 issues，空=无问题）。 */
    public interface LlmReviewHook {
        List<String> review(Map<String, Object> parsed, Map<String, Object> codeChecks);
    }

    private final LlmReviewHook llmHook;

    public ReviewService() {
        this(null);
    }

    public ReviewService(LlmReviewHook llmHook) {
        this.llmHook = llmHook;
    }

    /** 解析 + 审阅结果。 */
    public record Outcome(Map<String, Object> parsed, ReviewResult review) {}

    /**
     * 审阅 Planner 输出。
     *
     * @param rawOutput   Planner 原始 JSON
     * @param bundle      候选池（null 或空 → 跳过封闭世界校验）
     * @param budget      用户预算（>0 才校验）
     * @param days        期望天数
     * @param targetDays  局部模式被修改的天（非空 → 跳过全局天数检查）
     */
    public Outcome review(String rawOutput, ResearchBundle bundle,
                          int budget, int days, List<Integer> targetDays) {
        boolean isPartial = targetDays != null && !targetDays.isEmpty();
        Map<String, Object> checks = new HashMap<>();

        // Step 1: JSON 解析
        Map<String, Object> parsed = RepairJson.parse(rawOutput);
        if (parsed == null) {
            checks.put("json_parse", false);
            return new Outcome(null, ReviewResult.fail(
                "输出无法解析为合法 JSON",
                "你的输出不是合法 JSON。请严格按字段定义输出纯 JSON，不要 markdown 代码块。",
                checks));
        }
        checks.put("json_parse", true);

        // Step 2: 天数一致（局部模式跳过）
        @SuppressWarnings("unchecked")
        List<Object> itinerary = parsed.get("dailyItinerary") instanceof List
            ? (List<Object>) parsed.get("dailyItinerary") : List.of();
        int actualDays = itinerary.size();
        if (!isPartial && actualDays != days) {
            checks.put("days_match", false);
            return new Outcome(parsed, ReviewResult.fail(
                "行程天数不匹配：期望 " + days + " 天，实际 " + actualDays + " 天",
                "dailyItinerary 数组长度必须等于 " + days + "，当前为 " + actualDays + "。请调整。",
                checks));
        }
        checks.put("days_match", true);

        // Step 3: 预算 ≤1.15×
        Object totalBudget = parsed.get("totalBudget");
        if (totalBudget instanceof Number n && budget > 0) {
            double ratio = n.doubleValue() / budget;
            checks.put("budget_ratio", Math.round(ratio * 100.0) / 100.0);
            if (ratio > BUDGET_TOLERANCE) {
                return new Outcome(parsed, ReviewResult.fail(
                    "预算超标：规划 " + n.intValue() + " 元，用户预算 " + budget + " 元",
                    "总预算 " + n.intValue() + " 元超出用户预算 " + budget
                        + " 元。请压缩至 " + budget + " 元以内。",
                    checks));
            }
        }
        checks.put("budget_ok", true);

        // Step 4: budgetBreakdown 五键
        Object bd = parsed.get("budgetBreakdown");
        Map<String, Object> breakdown = bd instanceof Map ? (Map<String, Object>) bd : Map.of();
        List<String> missing = new ArrayList<>();
        for (String k : REQUIRED_BREAKDOWN_KEYS) {
            if (!breakdown.containsKey(k)) {
                missing.add(k);
            }
        }
        if (!missing.isEmpty()) {
            checks.put("breakdown_complete", false);
            return new Outcome(parsed, ReviewResult.fail(
                "budgetBreakdown 缺少字段：" + missing,
                "budgetBreakdown 必须包含 " + REQUIRED_BREAKDOWN_KEYS + " 五个数字字段，缺少：" + missing + "。",
                checks));
        }
        checks.put("breakdown_complete", true);

        // Step 5: 候选池封闭世界
        Set<String> pool = bundle != null ? bundle.allSpotNames() : Set.of();
        if (!pool.isEmpty()) {
            Set<String> tripSpots = new HashSet<>();
            for (Object dayObj : itinerary) {
                if (!(dayObj instanceof Map)) continue;
                Map<?, ?> day = (Map<?, ?>) dayObj;
                for (String period : PERIODS) {
                    Object slot = day.get(period);
                    if (slot instanceof Map && ((Map<?, ?>) slot).get("spot") != null) {
                        tripSpots.add(String.valueOf(((Map<?, ?>) slot).get("spot")));
                    }
                }
            }
            Set<String> unknown = new HashSet<>(tripSpots);
            unknown.removeAll(pool);
            if (!unknown.isEmpty()) {
                checks.put("pool_compliance", false);
                return new Outcome(parsed, ReviewResult.fail(
                    "以下景点不在候选池中：" + unknown,
                    "请仅使用候选池中的景点。以下景点不在候选池中：" + unknown,
                    checks));
            }
            checks.put("pool_compliance", true);
        } else {
            checks.put("pool_compliance", "no_pool");
        }

        // Step 6: LLM 二审（hook，warning 不打回）
        if (llmHook != null) {
            try {
                List<String> llmIssues = llmHook.review(parsed, checks);
                if (llmIssues != null && !llmIssues.isEmpty()) {
                    checks.put("llm_review", llmIssues);
                }
            } catch (Exception e) {
                log.warn("review|llm_layer_failed: {}", e.getMessage());
            }
        }

        return new Outcome(parsed, ReviewResult.passed(checks));
    }
}
