package com.trip.backend.service.agent;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.service.agent.dto.PlanRequest;
import com.trip.backend.service.agent.dto.PlanResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Orchestrator 编排内核（对应 Python orchestrator.py）。
 *
 * research → plan → review 三阶段 + 最多 2 轮重试循环，
 * 取代"单次 LLM 调用"。
 */
@Service
public class Orchestrator {

    private static final Logger log = LoggerFactory.getLogger(Orchestrator.class);
    private static final int MAX_REVIEW_RETRIES = 2;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final ResearchAgent researchAgent;
    private final PlannerAgent plannerAgent;
    private final ReviewService reviewService;

    public Orchestrator(ResearchAgent researchAgent,
                        PlannerAgent plannerAgent,
                        ReviewService reviewService) {
        this.researchAgent = researchAgent;
        this.plannerAgent = plannerAgent;
        this.reviewService = reviewService;
    }

    /** 规划全量行程（三阶段 + 重试）。 */
    public PlanResult plan(PlanRequest request) {
        long t0 = System.currentTimeMillis();
        log.info("[Orchestrator] 开始: city={}, days={}, budget={}",
            request.city(), request.days(), request.budget());

        // Phase 1: Research
        ResearchAgent.Output research = researchAgent.run(
            new ResearchAgent.Input(request.city(), request.days(), request.budget()));
        if (research.error() != null) {
            return PlanResult.error("Research 失败: " + research.error());
        }
        ResearchBundle bundle = research.bundle();

        // Phase 2+3: Plan → Review → 最多重试 2 次
        PlannerAgent.Input plannerInput =
            PlannerAgent.Input.first(bundle, request.city(), request.days(), request.budget());
        PlannerAgent.Output plannerOut = plannerAgent.run(plannerInput);
        if (plannerOut.error() != null) {
            return PlanResult.error("Planner 失败: " + plannerOut.error());
        }
        String raw = plannerOut.rawJson();

        ReviewResult reviewResult = null;
        Map<String, Object> parsed = null;
        for (int attempt = 0; attempt <= MAX_REVIEW_RETRIES; attempt++) {
            ReviewService.Outcome out = reviewService.review(
                raw, bundle, request.budget(), request.days(), null);
            reviewResult = out.review();
            parsed = out.parsed();
            if (reviewResult.passed()) {
                break;
            }
            // 最后一轮不再重试
            if (attempt >= MAX_REVIEW_RETRIES) {
                log.warn("[Orchestrator] review 最终未过: attempt={}, issues={}",
                    attempt + 1, reviewResult.issues());
                break;
            }
            // feedback 注入 planner 重跑
            log.info("[Orchestrator] review 打回 attempt={}, feedback={}",
                attempt + 1, reviewResult.feedback());
            plannerInput = plannerInput.withFeedback(reviewResult.feedback(), attempt + 1);
            plannerOut = plannerAgent.run(plannerInput);
            if (plannerOut.error() != null) {
                break;
            }
            raw = plannerOut.rawJson();
        }

        long duration = System.currentTimeMillis() - t0;
        log.info("[Orchestrator] 完成: duration={}ms, passed={}",
            duration, reviewResult != null && reviewResult.passed());

        if (parsed == null) {
            return PlanResult.error("行程解析失败");
        }
        return PlanResult.of(parsed);
    }

    /**
     * 局部修改：只重出指定天，merge 回原行程，未改天保留。
     */
    @SuppressWarnings("unchecked")
    public PlanResult modify(Map<String, Object> existingTrip,
                             String modifyRequest,
                             PlanRequest request,
                             List<Integer> targetDays) {
        List<Object> existingItinerary = existingTrip.get("dailyItinerary") instanceof List
            ? (List<Object>) existingTrip.get("dailyItinerary") : new ArrayList<>();

        // 局部模式：research 跳过
        ResearchBundle bundle = ResearchBundle.empty();

        PlannerAgent.Input plannerInput = new PlannerAgent.Input(
            bundle, request.city(), request.days(), request.budget(),
            "用户修改要求：" + modifyRequest, 0);
        PlannerAgent.Output plannerOut = plannerAgent.run(plannerInput);
        if (plannerOut.error() != null) {
            return PlanResult.error(plannerOut.error());
        }

        // 解析 planner 只重出的天，merge 回原行程
        Map<String, Object> partial = RepairJson.parse(plannerOut.rawJson());
        if (partial == null) {
            return PlanResult.error("修改方案无法解析");
        }
        Object merged = mergePartial(existingItinerary, partial, targetDays);

        Map<String, Object> finalPlan = new HashMap<>(existingTrip);
        finalPlan.put("dailyItinerary", merged);

        ReviewService.Outcome out = reviewService.review(
            toJson(finalPlan), bundle, request.budget(), request.days(), targetDays);
        if (!out.review().passed() || out.parsed() == null) {
            return PlanResult.error("修改方案未通过校验: " + out.review().issues());
        }
        return PlanResult.of(out.parsed());
    }

    /** 把 partial 中 targetDays 对应的天 merge 进 existing，其余天原样保留。 */
    @SuppressWarnings("unchecked")
    static List<Object> mergePartial(List<Object> existingItinerary,
                                     Map<String, Object> partial,
                                     List<Integer> targetDays) {
        List<Object> result = new ArrayList<>(existingItinerary);
        List<Object> partialItinerary = partial.get("dailyItinerary") instanceof List
            ? (List<Object>) partial.get("dailyItinerary") : List.of();

        for (Object pDayObj : partialItinerary) {
            if (!(pDayObj instanceof Map)) continue;
            Map<String, Object> pDay = (Map<String, Object>) pDayObj;
            int dayNum = pDay.get("day") instanceof Number ? ((Number) pDay.get("day")).intValue() : -1;
            if (dayNum < 1 || !targetDays.contains(dayNum)) continue;
            // 替换 result 中第 dayNum-1 位
            int idx = dayNum - 1;
            if (idx < result.size()) {
                result.set(idx, pDay);
            } else {
                result.add(pDay);
            }
        }
        return result;
    }

    private String toJson(Map<String, Object> m) {
        try {
            return MAPPER.writeValueAsString(m);
        } catch (Exception e) {
            return "{}";
        }
    }
}
