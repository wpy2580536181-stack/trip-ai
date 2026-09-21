package com.trip.backend.service.agent.tools;

import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D5 工具契约测试（对应 backlog ToolContractTest）。
 *
 * 判定：
 *  1. 7 个业务工具参数名/输出/fallback 逐条断言（MCP 3 个在 J-D6 并入后补全为 10）。
 *  2. 熔断三态 CLOSED→OPEN→HALF_OPEN→CLOSED。
 *  3. 429 按 Retry-After 退避（封顶 30s）；其它指数退避封顶 10s。
 *  4. 工具缓存：字面 key 命中（字段顺序无关）+ 向量相似度 ≥0.85 命中。
 */
class ToolContractTest {

    private ToolSpecRegistry registry() {
        return new ToolSpecRegistry(List.of(
            new RetrieveKnowledgeTool(null),
            new SearchHotelsTool(null),
            new CalculateDistanceTool(),
            new MeituanTool()
        ));
    }

    // ---- 判定 1：工具契约 ----
    @Test
    void allBusinessToolsRegisteredWithCorrectFallback() {
        ToolSpecRegistry reg = registry();
        // 4 个 Spring bean + 3 个通勤 = 7 个业务工具
        assertEquals(7, reg.size(), "当前业务工具 7 个（MCP 3 个 J-D6 并入后为 10）");

        // retrieve_knowledge
        AgentTool rk = reg.get("retrieve_knowledge");
        assertNotNull(rk);
        assertEquals("知识库暂时不可用，请基于通用旅行知识回答。", rk.fallback());
        assertTrue(rk.spec().parametersSchema().contains("\"query\""));
        assertTrue(rk.spec().parametersSchema().contains("\"city\""));
        assertTrue(rk.spec().parametersSchema().contains("\"category\""));

        // search_hotels
        AgentTool sh = reg.get("search_hotels");
        assertEquals("住宿信息暂时不可用，请基于通用旅行知识回答。", sh.fallback());
        assertTrue(sh.spec().parametersSchema().contains("\"city\""));
        assertTrue(sh.spec().parametersSchema().contains("\"budget\""));
        assertTrue(sh.spec().parametersSchema().contains("\"level\""));

        // calculate_distance
        AgentTool cd = reg.get("calculate_distance");
        assertEquals("距离计算暂时不可用。", cd.fallback());
        assertTrue(cd.spec().parametersSchema().contains("\"from_city\""));
        assertTrue(cd.spec().parametersSchema().contains("\"to_city\""));
        assertTrue(cd.spec().parametersSchema().contains("\"mode\""));

        // commute 三件套
        assertEquals("{\"error\": \"通勤路线规划暂时不可用，请稍后再试。\"}",
            reg.get("compute_optimal_commute").fallback());
        assertEquals("{\"error\": \"地点联想暂时不可用。\"}",
            reg.get("search_commute_tips").fallback());
        assertEquals("{\"error\": \"周边 POI 查询暂时不可用。\"}",
            reg.get("search_nearby_commute_pois").fallback());

        // meituan
        AgentTool mt = reg.get("meituan_query");
        assertTrue(mt.spec().parametersSchema().contains("\"query\""));
        assertTrue(mt.spec().parametersSchema().contains("\"origin_query\""));
        assertTrue(mt.spec().parametersSchema().contains("\"city\""));
    }

    @Test
    void calculateDistanceComputesHaversineEstimate() {
        ToolSpecRegistry reg = registry();
        // 北京 → 上海，flight
        String out = reg.call("calculate_distance", Map.of("from_city", "北京", "to_city", "上海"));
        assertTrue(out.contains("直线距离") && out.contains("飞机"), out);
        // 未知城市 → 友好文案（不抛）
        String unknown = reg.call("calculate_distance", Map.of("from_city", "火星", "to_city", "北京"));
        assertTrue(unknown.contains("暂不支持城市"), unknown);
    }

    @Test
    void meituanWithoutTokenReturnsGuidanceNotCrash() {
        ToolSpecRegistry reg = registry();
        // 未配 MEITUAN_HT_TOKEN → 明确文案（不抛异常）
        String out = reg.call("meituan_query", Map.of("query", "北京酒店"));
        assertTrue(out.contains("MEITUAN_HT_TOKEN") || out.contains("美团"), out);
    }

    // ---- 判定 2：熔断三态 ----
    @Test
    void circuitBreakerTransitionsClosedOpenHalfOpenClosed() throws Exception {
        CircuitBreaker cb = CircuitBreaker.getOrCreate("test_circuit", 5, 200);
        cb.reset();
        assertEquals(CircuitBreaker.State.CLOSED, cb.state());

        // 连续 5 次失败 → OPEN
        for (int i = 0; i < 5; i++) {
            cb.recordFailure();
        }
        assertEquals(CircuitBreaker.State.OPEN, cb.state(), "连续 5 次失败 → OPEN");
        assertTrue(!cb.allowRequest(), "OPEN 状态拒绝请求");

        Thread.sleep(250); // 超过 recovery_timeout
        assertTrue(cb.allowRequest(), "恢复窗口后 → HALF_OPEN 放行试探");
        assertEquals(CircuitBreaker.State.HALF_OPEN, cb.state());

        cb.recordSuccess();
        assertEquals(CircuitBreaker.State.CLOSED, cb.state(), "试探成功 → CLOSED");

        // 试探失败 → 回 OPEN
        for (int i = 0; i < 5; i++) {
            cb.recordFailure();
        }
        assertEquals(CircuitBreaker.State.OPEN, cb.state());
        cb.reset();
    }

    // ---- 判定 3：429 Retry-After 退避 ----
    @Test
    void backoffUsesRetryAfterCappedAt30s() {
        ResilienceWrapper w = new ResilienceWrapper(5, 2, "fb", null);
        // 429 retryAfter=10 → 10
        assertEquals(10, w.backoffSeconds(new RateLimitException(10), 0));
        // 429 retryAfter=60 → 封顶 30
        assertEquals(30, w.backoffSeconds(new RateLimitException(60), 0));
        // 普通异常指数退避：attempt0=1, attempt1=2, 封顶 10
        assertEquals(1, w.backoffSeconds(new RuntimeException("boom"), 0));
        assertEquals(2, w.backoffSeconds(new RuntimeException("boom"), 1));
    }

    @Test
    void toolFailureReturnsFallbackNotThrow() {
        ToolSpecRegistry reg = registry();
        // commute 工具 MCP 未接 → execute 抛异常 → wrapper 返回 fallback JSON
        String out = reg.call("compute_optimal_commute", Map.of("origin", "家"));
        assertTrue(out.contains("通勤路线规划暂时不可用"), out);
    }

    // ---- 判定 4：工具缓存 ----
    @Test
    void toolCacheLiteralKeyOrderInsensitive() {
        ToolCache cache = new ToolCache(300, 100);
        Map<String, Object> a = new LinkedHashMap<>();
        a.put("city", "北京");
        a.put("query", "故宫");
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("query", "故宫");
        b.put("city", "北京");

        assertEquals(cache.literalKey("retrieve_knowledge", a),
            cache.literalKey("retrieve_knowledge", b), "字段顺序不同 key 应相同");

        String key = cache.literalKey("retrieve_knowledge", a);
        assertNull(cache.getLiteral(key));
        cache.put(key, "cached-value", null);
        assertEquals("cached-value", cache.getLiteral(key));
    }

    @Test
    void toolCacheVectorSimilarityHitThreshold() {
        ToolCache cache = new ToolCache(300, 100);
        // 两个已归一化向量：相似度 0.95 ≥ 0.85 应命中
        float[] v1 = normalized(1, 0);
        float[] v2 = normalized(0.95f, 0.31225f); // cos≈0.95
        cache.put("k1", "result-v1", v1);

        String hit = cache.getByVector(v2, 0.85);
        assertEquals("result-v1", hit, "相似度 ≥0.85 应命中");

        float[] far = normalized(0, 1); // 与 v1 cos≈0
        assertNull(cache.getByVector(far, 0.85), "相似度 <0.85 不应命中");
    }

    private static float[] normalized(float... vals) {
        double norm = 0;
        for (float v : vals) norm += v * v;
        double n = Math.sqrt(norm);
        float[] out = new float[vals.length];
        for (int i = 0; i < vals.length; i++) out[i] = (float) (vals[i] / n);
        return out;
    }
}
