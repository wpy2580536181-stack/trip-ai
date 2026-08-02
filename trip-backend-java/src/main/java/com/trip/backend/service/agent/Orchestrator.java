package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * Orchestrator 编排器
 *
 * 对应 Python services/agent/orchestrator.py
 *
 * 职责：
 * - 调度 ResearchAgent / PlannerAgent / ReviewService
 * - 管理重试循环（MAX_REVIEW_RETRIES=2）
 * - 汇总 Token 用量
 * - 纯编排，不含 LLM 调用
 */
@Service
public class Orchestrator {

    private static final Logger log = LoggerFactory.getLogger(Orchestrator.class);
    private static final int MAX_REVIEW_RETRIES = 2;

    private final ResearchAgent researchAgent;
    private final PlannerAgent plannerAgent;
    private final ReviewService reviewService;

    public Orchestrator(
            ResearchAgent researchAgent,
            PlannerAgent plannerAgent,
            ReviewService reviewService) {
        this.researchAgent = researchAgent;
        this.plannerAgent = plannerAgent;
        this.reviewService = reviewService;
    }

    /**
     * 全量规划流程（plan 模式）
     *
     * 流程：Research → Plan → Review（重试循环）
     *
     * @param request 计划请求
     * @return 计划结果
     */
    public CompletableFuture<PlanResult> plan(PlanRequest request) {
        long startTime = System.currentTimeMillis();

        return CompletableFuture.supplyAsync(() -> {
            try {
                log.info("[Orchestrator] Starting plan flow: city={}, days={}, budget={}",
                    request.city(), request.days(), request.budget());

                // 1. Research 阶段
                emitProgress("research", "start");
                ResearchInput researchInput = new ResearchInput(
                    request.city(),
                    request.days(),
                    request.budget(),
                    request.departureCity(),
                    request.interests()
                );
                ResearchBundle researchBundle = researchAgent.research(researchInput).join();
                emitProgress("research", "done");

                // 2. Plan + Review 循环
                TokenUsage totalUsage = TokenUsage.empty();
                Map<String, Object> plan = null;
                ReviewResult review = null;
                String feedback = null;

                for (int attempt = 0; attempt <= MAX_REVIEW_RETRIES; attempt++) {
                    log.info("[Orchestrator] Plan attempt {}/{}", attempt + 1, MAX_REVIEW_RETRIES + 1);

                    // Plan 阶段
                    emitProgress("plan", "start", Map.of("attempt", attempt + 1));
                    PlannerInput plannerInput = feedback != null
                        ? PlannerInput.withFeedback(researchBundle, feedback)
                        : PlannerInput.full(researchBundle);

                    CompletableFuture<Map<String, Object>> planFuture = plannerAgent.plan(plannerInput);
                    plan = planFuture.join();
                    emitProgress("plan", "done", Map.of("attempt", attempt + 1));

                    // 累加 Token 用量
                    totalUsage = totalUsage.merge(plannerAgent.getLastUsage());

                    // Review 阶段
                    emitProgress("review", "start", Map.of("attempt", attempt + 1));
                    review = reviewService.review(plan, request.budget());
                    emitProgress("review", "done", Map.of(
                        "attempt", attempt + 1,
                        "passed", review.passed()
                    ));

                    if (review.passed()) {
                        log.info("[Orchestrator] Review passed on attempt {}", attempt + 1);
                        break;
                    }

                    // 未通过，提取 feedback
                    if (attempt < MAX_REVIEW_RETRIES) {
                        feedback = String.join("; ", review.issues());
                        log.warn("[Orchestrator] Review failed (attempt {}): {}, retrying with feedback",
                            attempt + 1, feedback);
                    }
                }

                // 3. 保存行程
                emitProgress("save", "start");
                // TODO: D7 实现后补充 trip 落库逻辑
                emitProgress("save", "done");

                long durationMs = System.currentTimeMillis() - startTime;
                log.info("[Orchestrator] Plan flow completed in {}ms", durationMs);

                return PlanResult.of(plan, review, totalUsage);

            } catch (Exception e) {
                log.error("[Orchestrator] Plan flow failed", e);
                throw new RuntimeException("Orchestrator failed: " + e.getMessage(), e);
            }
        });
    }

    /**
     * 修改流程（modify 模式）
     *
     * @param request 修改请求
     * @return 修改结果
     */
    public CompletableFuture<PlanResult> modify(PlanRequest request, Long parentTripId, List<Integer> targetDays) {
        // TODO: D7 实现后补充
        return CompletableFuture.failedFuture(new UnsupportedOperationException("modify not implemented yet"));
    }

    /**
     * 发送进度事件
     */
    private void emitProgress(String stage, String status) {
        emitProgress(stage, status, Map.of());
    }

    private void emitProgress(String stage, String status, Map<String, Object> extra) {
        // TODO: D7 集成 EventSink 后实现
        log.debug("[Orchestrator] Progress: stage={}, status={}, extra={}", stage, status, extra);
    }
}
