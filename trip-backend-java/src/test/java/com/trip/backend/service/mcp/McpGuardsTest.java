package com.trip.backend.service.mcp;

import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D6 MCP Guards 判定测试。
 *
 * 判定：
 *  2. 连续 5 次失败 → 熔断 OPEN；60s 后半开试探成功恢复。
 *  3. 令牌桶超 3/s → 报错。
 *  4. mcp-stats 快照字段（calls/successes/failures/cacheHits/circuitOpenCount/avgDurationMs）齐全。
 *
 * 判定 1（smoke：真实 npx+AMAP key）见 McpSmokeTest，无环境时自动跳过。
 */
class McpGuardsTest {

    // ---- 判定 2：熔断 ----
    @Test
    void fiveFailuresOpenCircuitAndHalfOpenRecover() throws Exception {
        // 恢复窗口 200ms（生产 60s）
        Guards guards = new Guards(5, 200, 3.0, 5, 1800);
        AtomicInteger calls = new AtomicInteger();

        // 连续 5 次失败 → OPEN
        for (int i = 0; i < 5; i++) {
            assertThrows(RuntimeException.class, () ->
                guards.call("maps_weather", "k", () -> {
                    calls.incrementAndGet();
                    throw new RuntimeException("down");
                }));
        }
        assertTrue(guards.circuitIsOpen(), "连续 5 次失败 → OPEN");
        assertEquals(5, calls.get(), "OPEN 前确实调了 5 次");

        // OPEN 期间直接拒绝（不再调下游）
        assertThrows(RuntimeException.class, () ->
            guards.call("maps_weather", "k", () -> {
                calls.incrementAndGet();
                return "should-not-run";
            }));
        assertEquals(5, calls.get(), "OPEN 期间不调下游");

        Thread.sleep(1100); // 超过 60s 恢复窗口（测试注入 200ms），同时让令牌桶补充（3/s）
        // 半开试探成功 → CLOSED
        String ok = guards.call("maps_weather", "k", () -> "ok-after-recovery");
        assertEquals("ok-after-recovery", ok);
        assertTrue(!guards.circuitIsOpen(), "试探成功 → CLOSED");
    }

    // ---- 判定 3：令牌桶限流 ----
    @Test
    void tokenBucketRejectsWhenRateExceeded() {
        Guards.TokenBucket bucket = new Guards.TokenBucket(3.0, 5);
        // capacity=5：前 5 个都成功（桶满）
        int accepted = 0;
        for (int i = 0; i < 5; i++) {
            if (bucket.tryAcquire()) accepted++;
        }
        assertEquals(5, accepted, "桶满 5 个令牌前 5 次应成功");
        // 第 6 次瞬间：桶已空 → 拒绝
        assertTrue(!bucket.tryAcquire(), "瞬时超过 capacity 应限流");
    }

    // ---- 判定 4：指标快照 ----
    @Test
    void metricsSnapshotHasAllFields() throws Exception {
        Guards guards = new Guards(5, 60_000, 3.0, 5, 1800);
        guards.resetMetrics();

        // 1 次成功（maps_geo 可缓存）
        guards.call("maps_geo", "beijing", () -> "geo-result");
        // 同 key 再调 → 缓存命中
        guards.call("maps_geo", "beijing", () -> "should-not-run");
        // 1 次失败
        assertThrows(RuntimeException.class, () ->
            guards.call("maps_weather", "x", () -> { throw new RuntimeException("boom"); }));

        Guards.Metrics snap = guards.snapshot();
        assertEquals(3, snap.calls, "calls=3");
        assertEquals(2, snap.successes, "successes=2（1 真实 + 1 缓存命中）");
        assertEquals(1, snap.failures, "failures=1");
        assertEquals(1, snap.cacheHits, "cacheHits=1");
        assertNotNull(snap.avgDurationMs);
        // circuitOpenCount：失败未到阈值，应为 0
        assertEquals(0, snap.circuitOpenCount);
    }

    @Test
    void cacheOnlyForWeatherAndGeo() throws Exception {
        Guards guards = new Guards(5, 60_000, 3.0, 5, 1800);
        guards.resetMetrics();

        // 不可缓存工具（maps_direction）两次都真实执行
        guards.call("maps_direction", "k", () -> "a");
        guards.call("maps_direction", "k", () -> "b");
        assertEquals(0, guards.snapshot().cacheHits, "非可缓存工具不写缓存");
    }
}
