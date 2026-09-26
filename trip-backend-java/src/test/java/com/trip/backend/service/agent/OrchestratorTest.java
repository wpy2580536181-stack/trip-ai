package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.PlanRequest;
import com.trip.backend.service.agent.dto.PlanResult;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D7 编排内核判定测试（stub LLM，不调真模型）。
 *
 *  1. 三阶段顺序 research→plan→review
 *  2. review 失败 → feedback 注入重跑，最多 2 次收敛
 *  3. 预算超 15% → 打回
 *  4. 候选池外 spot → 打回
 *  5. modify 局部：未改天原样保留
 */
class OrchestratorTest {

    /** 记录阶段调用顺序的 stub。 */
    static class RecordingResearch implements ResearchAgent {
        final List<String> calls = new ArrayList<>();
        final ResearchBundle bundle;
        RecordingResearch(ResearchBundle b) { this.bundle = b; }
        @Override public Output run(Input input) {
            calls.add("research");
            return Output.ok(bundle);
        }
    }

    /** 脚本化 Planner：按 script 顺序返回，记录每次 feedback。 */
    static class ScriptedPlanner implements PlannerAgent {
        final List<String> script;
        final List<String> feedbacks = new ArrayList<>();
        final List<String> calls = new ArrayList<>();
        int idx = 0;
        ScriptedPlanner(String... outputs) { this.script = List.of(outputs); }
        @Override public Output run(Input input) {
            calls.add("plan");
            feedbacks.add(input.feedback());
            return Output.ok(script.get(Math.min(idx++, script.size() - 1)));
        }
    }

    /** 一个合法 plan JSON 工厂。 */
    static String goodJson(int days, int totalBudget, String... spots) {
        List<Map<String, Object>> itinerary = new ArrayList<>();
        for (int d = 1; d <= days; d++) {
            String spot = spots.length >= d ? spots[d - 1] : "景点" + d;
            Map<String, Object> day = new LinkedHashMap<>();
            day.put("day", d);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("spot", spot);
            m.put("duration", "2小时");
            m.put("ticket", "0");
            day.put("morning", m);
            itinerary.add(day);
        }
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("city", "北京");
        plan.put("days", days);
        plan.put("totalBudget", totalBudget);
        plan.put("dailyItinerary", itinerary);
        plan.put("budgetBreakdown", Map.of(
            "accommodation", 200, "food", 200, "transportation", 100, "tickets", 100, "other", 100));
        plan.put("tips", List.of());
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(plan);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    // ---- 判定 1：三阶段顺序 ----
    @Test
    void threeStagesInOrder() {
        RecordingResearch research = new RecordingResearch(ResearchBundle.empty());
        ScriptedPlanner planner = new ScriptedPlanner(goodJson(3, 800, "A", "B", "C"));
        ReviewService review = new ReviewService();

        Orchestrator orch = new Orchestrator(research, planner, review);
        PlanResult r = orch.plan(new PlanRequest("北京", 3, 1000));

        assertNotNull(r.plan());
        assertFalse(r.plan().containsKey("error"), "不应报错: " + r.plan());
        // research 先于 plan
        assertEquals(0, research.calls.indexOf("research"));
        assertTrue(planner.calls.size() >= 1);
        // review 通过 → planner 只调 1 次
        assertEquals(1, planner.calls.size(), "一次通过不应重试");
    }

    // ---- 判定 2：review 失败 → feedback 注入重跑，最多 2 次收敛 ----
    @Test
    void reviewFailureRetriesWithFeedbackUpToTwoTimes() {
        RecordingResearch research = new RecordingResearch(ResearchBundle.empty());
        // 第 1 次：超预算（1500 > 1000×1.15）；第 2 次：合规
        ScriptedPlanner planner = new ScriptedPlanner(
            goodJson(3, 1500, "A", "B", "C"),
            goodJson(3, 900, "A", "B", "C"));
        ReviewService review = new ReviewService();

        Orchestrator orch = new Orchestrator(research, planner, review);
        PlanResult r = orch.plan(new PlanRequest("北京", 3, 1000));

        assertFalse(r.plan().containsKey("error"));
        assertEquals(2, planner.calls.size(), "第 1 次被打回，应重试 1 次后收敛");
        // 第 2 次调用必须带 feedback
        assertFalse(planner.feedbacks.get(1).isBlank(), "重试时 feedback 必须注入 planner");
        assertTrue(planner.feedbacks.get(1).contains("预算") || planner.feedbacks.get(1).contains("压缩"),
            "feedback 应说明预算问题: " + planner.feedbacks.get(1));
    }

    @Test
    void givesUpAfterTwoRetries() {
        RecordingResearch research = new RecordingResearch(ResearchBundle.empty());
        // 每次都超预算 → 最终失败但只重试 2 次
        ScriptedPlanner planner = new ScriptedPlanner(goodJson(3, 2000, "A", "B", "C"));
        ReviewService review = new ReviewService();
        Orchestrator orch = new Orchestrator(research, planner, review);
        orch.plan(new PlanRequest("北京", 3, 1000));
        // attempt 0,1,2 → planner 调 3 次（首跑 + 2 次重试）
        assertEquals(3, planner.calls.size(), "最多重试 2 次 = 共 3 次 planner 调用");
    }

    // ---- 判定 3：预算超 15% → 打回 ----
    @Test
    void budgetOver15PercentRejected() {
        ReviewService review = new ReviewService();
        // 1200 / 1000 = 1.2 > 1.15
        ReviewService.Outcome out = review.review(goodJson(3, 1200, "A", "B", "C"),
            ResearchBundle.empty(), 1000, 3, null);
        assertFalse(out.review().passed());
        assertTrue(out.review().issues().get(0).contains("预算超标"));

        // 1150 / 1000 = 1.15 恰好边界 → 通过
        ReviewService.Outcome ok = review.review(goodJson(3, 1150, "A", "B", "C"),
            ResearchBundle.empty(), 1000, 3, null);
        assertTrue(ok.review().passed(), "≤1.15 应通过");
    }

    // ---- 判定 4：候选池外 spot → 打回 ----
    @Test
    void spotOutsidePoolRejected() {
        ResearchBundle bundle = new ResearchBundle(Set.of("故宫", "天安门"), "", "", "", "", "", java.util.List.of());
        ReviewService review = new ReviewService();
        // 用了池外"迪士尼"
        ReviewService.Outcome out = review.review(goodJson(2, 800, "故宫", "迪士尼"),
            bundle, 1000, 2, null);
        assertFalse(out.review().passed());
        assertTrue(out.review().issues().get(0).contains("迪士尼"),
            "应指出池外景点: " + out.review().issues());
    }

    // ---- 判定 5：modify 局部模式未改天保留 ----
    @Test
    void modifyPartialPreservesUnmodifiedDays() {
        RecordingResearch research = new RecordingResearch(ResearchBundle.empty());
        // planner 只重出 day2
        String partial = goodJson(1, 500, "新景点");
        // 修正：partial 只含 day2 一条
        Map<String, Object> partialPlan = new HashMap<>();
        partialPlan.put("city", "北京");
        partialPlan.put("days", 3);
        partialPlan.put("totalBudget", 900);
        partialPlan.put("dailyItinerary", List.of(Map.of(
            "day", 2,
            "morning", Map.of("spot", "新景点", "duration", "3小时", "ticket", "100"))));
        partialPlan.put("budgetBreakdown", Map.of(
            "accommodation", 200, "food", 200, "transportation", 100, "tickets", 100, "other", 100));
        String partialJson;
        try {
            partialJson = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(partialPlan);
        } catch (Exception e) { throw new RuntimeException(e); }

        ScriptedPlanner planner = new ScriptedPlanner(partialJson);
        ReviewService review = new ReviewService();
        Orchestrator orch = new Orchestrator(research, planner, review);

        Map<String, Object> existing = new HashMap<>();
        existing.put("city", "北京");
        existing.put("days", 3);
        existing.put("totalBudget", 900);
        existing.put("dailyItinerary", List.of(
            Map.of("day", 1, "morning", Map.of("spot", "原景点1", "duration", "2小时", "ticket", "0")),
            Map.of("day", 2, "morning", Map.of("spot", "原景点2", "duration", "2小时", "ticket", "0")),
            Map.of("day", 3, "morning", Map.of("spot", "原景点3", "duration", "2小时", "ticket", "0"))
        ));
        existing.put("budgetBreakdown", Map.of(
            "accommodation", 200, "food", 200, "transportation", 100, "tickets", 100, "other", 100));

        PlanResult r = orch.modify(existing, "第二天换个景点", new PlanRequest("北京", 3, 1000), List.of(2));
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> resultItinerary = (List<Map<String, Object>>) r.plan().get("dailyItinerary");
        assertEquals(3, resultItinerary.size());
        // day1/day3 原样
        assertEquals("原景点1", ((Map<?,?>) resultItinerary.get(0).get("morning")).get("spot"));
        assertEquals("原景点3", ((Map<?,?>) resultItinerary.get(2).get("morning")).get("spot"));
        // day2 被替换
        assertEquals("新景点", ((Map<?,?>) resultItinerary.get(1).get("morning")).get("spot"));
    }
}
