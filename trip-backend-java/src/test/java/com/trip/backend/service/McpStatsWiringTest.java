package com.trip.backend.service;

import com.trip.backend.service.mcp.Guards;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-B5x 判定 2：mcp-stats 的 calls/failures/circuitOpenCount 随真实调用变化。
 * （判定 1 /api/feedback/stats 真实计数为 [需真实环境]）
 */
class McpStatsWiringTest {

    @Test
    void mcpStatsReflectsGuardsCalls() {
        Guards guards = new Guards(5, 60_000, 3.0, 5, 1800);
        StatsService stats = new StatsService(null, null, guards);

        // 初始全 0
        Map<String, Object> before = stats.getMcpStats();
        assertEquals(0L, before.get("calls"));

        // 成功调一次
        guards.call("maps_direction", null, () -> "ok");
        // 失败调一次
        try {
            guards.call("maps_direction", null, () -> { throw new RuntimeException("boom"); });
        } catch (RuntimeException ignored) {}

        Map<String, Object> after = stats.getMcpStats();
        assertEquals(2L, after.get("calls"), "calls 应随调用增长");
        assertEquals(1L, after.get("successes"));
        assertEquals(1L, after.get("failures"));
        assertTrue(((Number) after.get("avgDurationMs")).doubleValue() >= 0);
    }
}
