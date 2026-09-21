package com.trip.backend.service.agent;

import com.trip.backend.service.agent.card.CardEventBuilder;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D8 对话内核判定（mock 意图解析）。
 *
 *  1. 四工具触发与降级正确
 *  2. 卡片事件结构：info_text≤1500、poi_list≤10、commute_compare≤5
 *  3. trip_planned/trip_diff 事件字段正确（TripPersistenceTest）
 */
class ChatAgentToolTest {

    // ---- 判定 2：卡片结构 ----
    @Test
    void cardRespectsLimits() {
        String longText = "字".repeat(2000);
        List<Object> poiList = new ArrayList<>();
        for (int i = 0; i < 20; i++) poiList.add("poi" + i);
        List<Object> commute = new ArrayList<>();
        for (int i = 0; i < 9; i++) commute.add("方案" + i);

        @SuppressWarnings("unchecked")
        Map<String, Object> card = (Map<String, Object>) CardEventBuilder.buildCard(
            "poi_list", longText, poiList, commute);

        assertEquals(1500, ((String) card.get("info_text")).length(),
            "info_text 应截到 1500");
        assertEquals(10, ((List<?>) card.get("poi_list")).size(),
            "poi_list 应截到 10");
        assertEquals(5, ((List<?>) card.get("commute_compare")).size(),
            "commute_compare 9>5 应截到 5");
    }

    @Test
    void commuteCompareCappedAtFive() {
        List<Object> c = new ArrayList<>();
        for (int i = 0; i < 9; i++) c.add("x");
        @SuppressWarnings("unchecked")
        Map<String, Object> card = (Map<String, Object>) CardEventBuilder.buildCard("commute", "t", null, c);
        assertEquals(5, ((List<?>) card.get("commute_compare")).size());
    }

    // ---- 判定 1：预检测 commute ----
    @Test
    void commuteQueryShortCircuits() {
        TripPersistenceService persistence = new TripPersistenceService(t -> { t.setId(1L); return t; });
        AgentEngine engine = new AgentEngine(null, persistence, m -> new TriggerTools.Intent.Chat(m));
        Map<String, Object> out = engine.chat(1L, "附近有什么地铁站？", 1L);
        assertEquals("commute", out.get("branch"));
    }

    @Test
    void planIntentDispatchesToOrchestrator() {
        // stub orchestrator：构造时传入真实 Orchestrator，但用 stub Research/Planner
        RecordingResearch research = new RecordingResearch(ResearchBundle.empty());
        ScriptedPlanner planner = new ScriptedPlanner(
            goodJson(2, 800, "A", "B"));
        ReviewService review = new ReviewService();
        Orchestrator orch = new Orchestrator(research, planner, review);

        List<Long> savedIds = new ArrayList<>();
        TripPersistenceService persistence = new TripPersistenceService(t -> {
            t.setId((long) (savedIds.size() + 1));
            savedIds.add(t.getId());
            return t;
        });

        // 意图解析：返回 PlanIntent
        AgentEngine engine = new AgentEngine(orch, persistence,
            m -> new TriggerTools.Intent.Plan(new TriggerTools.PlanIntent("北京", 2, 1000)));
        Map<String, Object> out = engine.chat(7L, "帮我规划北京2日游", 1L);

        assertEquals("trigger_plan", out.get("branch"));
        assertTrue(out.get("tripId") instanceof Long, "应返回真实 tripId");
        assertEquals(1, savedIds.size(), "应落库 1 行");
    }

    @Test
    void unknownIntentDegradesToChat() {
        TripPersistenceService persistence = new TripPersistenceService(t -> { t.setId(1L); return t; });
        AgentEngine engine = new AgentEngine(null, persistence,
            m -> new TriggerTools.Intent.Chat(m));
        Map<String, Object> out = engine.chat(1L, "你好", 1L);
        assertEquals("chat", out.get("branch"));
    }

    // ---- 复用 OrchestratorTest 的 stub ----
    static class RecordingResearch implements ResearchAgent {
        final ResearchBundle bundle;
        RecordingResearch(ResearchBundle b) { this.bundle = b; }
        @Override public Output run(Input input) { return Output.ok(bundle); }
    }
    static class ScriptedPlanner implements PlannerAgent {
        final List<String> script; int idx = 0;
        ScriptedPlanner(String... o) { this.script = List.of(o); }
        @Override public Output run(Input input) {
            return Output.ok(script.get(Math.min(idx++, script.size() - 1)));
        }
    }
    static String goodJson(int days, int totalBudget, String... spots) {
        try {
            var itinerary = new ArrayList<Map<String, Object>>();
            for (int d = 1; d <= days; d++) {
                String spot = spots.length >= d ? spots[d - 1] : "景点" + d;
                itinerary.add(Map.of("day", d, "morning",
                    Map.of("spot", spot, "duration", "2h", "ticket", "0")));
            }
            Map<String, Object> plan = new java.util.LinkedHashMap<>();
            plan.put("city", "北京");
            plan.put("days", days);
            plan.put("totalBudget", totalBudget);
            plan.put("dailyItinerary", itinerary);
            plan.put("budgetBreakdown", Map.of(
                "accommodation", 200, "food", 200, "transportation", 100, "tickets", 100, "other", 100));
            plan.put("tips", List.of());
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(plan);
        } catch (Exception e) { throw new RuntimeException(e); }
    }
}
