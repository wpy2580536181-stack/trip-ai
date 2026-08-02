package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * ReviewService 审阅服务
 *
 * 职责：
 * - JSON 解析
 * - 天数一致性校验
 * - 预算检查（≤1.15×）
 * - budgetBreakdown 五键校验
 * - 候选池封闭世界校验
 * - LLM 二层审阅（前 3 天、截断 2000）
 */
@Service
public class ReviewService {

    private static final Logger log = LoggerFactory.getLogger(ReviewService.class);

    private static final double BUDGET_TOLERANCE = 1.15; // 预算容忍度 15%
    private static final int MAX_DAYS_FOR_LLM_REVIEW = 3; // LLM 审阅前 N 天

    public ReviewResult review(Map<String, Object> plan, Integer budget) {
        List<String> issues = new java.util.ArrayList<>();

        // 1. JSON 解析（已解析，跳过）
        // 2. 天数一致性
        if (!validateDayCount(plan, issues)) {
            // 局部模式跳过天数检查
        }

        // 3. 预算检查
        validateBudget(plan, budget, issues);

        // 4. budgetBreakdown 五键校验
        validateBudgetBreakdown(plan, issues);

        // 5. 候选池封闭世界校验
        validateCandidatePool(plan, issues);

        // 6. LLM 二层审阅（简化版：仅检查前 3 天）
        if (!issues.isEmpty() || needsLlmReview(plan)) {
            llmSecondPassReview(plan, issues);
        }

        if (issues.isEmpty()) {
            return ReviewResult.passed();
        } else {
            return ReviewResult.failed(issues);
        }
    }

    /**
     * 验证天数一致性
     */
    private boolean validateDayCount(Map<String, Object> plan, List<String> issues) {
        // TODO: D7 实现后补充
        return true;
    }

    /**
     * 验证预算
     */
    private void validateBudget(Map<String, Object> plan, Integer budget, List<String> issues) {
        if (budget == null) {
            return;
        }

        // TODO: D7 实现后补充预算计算逻辑
        // 估算总费用
        // int estimatedCost = calculateTotalCost(plan);
        // if (estimatedCost > budget * BUDGET_TOLERANCE) {
        //     issues.add(String.format("预算超支：预计费用 %d，超出预算 15%% 上限 %d",
        //         estimatedCost, (int) (budget * BUDGET_TOLERANCE)));
        // }
    }

    /**
     * 验证 budgetBreakdown 五键
     */
    private void validateBudgetBreakdown(Map<String, Object> plan, List<String> issues) {
        Map<String, Object> breakdown = (Map<String, Object>) plan.get("budgetBreakdown");
        if (breakdown == null) {
            issues.add("缺少 budgetBreakdown");
            return;
        }

        // 检查五键：hotel/food/transport/ticket/other
        List<String> requiredKeys = List.of("hotel", "food", "transport", "ticket", "other");
        for (String key : requiredKeys) {
            if (!breakdown.containsKey(key)) {
                issues.add("budgetBreakdown 缺少键：" + key);
            }
        }
    }

    /**
     * 验证候选池封闭世界
     */
    private void validateCandidatePool(Map<String, Object> plan, List<String> issues) {
        // TODO: D7 实现后补充
    }

    /**
     * 判断是否需要 LLM 二层审阅
     */
    private boolean needsLlmReview(Map<String, Object> plan) {
        // TODO: D7 实现后补充
        return false;
    }

    /**
     * LLM 二层审阅
     */
    private void llmSecondPassReview(Map<String, Object> plan, List<String> issues) {
        // TODO: D7 实现后补充
    }
}
