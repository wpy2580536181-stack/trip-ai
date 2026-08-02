package com.trip.backend.service.mcp;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * McpStatsTest - MCP 指标快照测试
 */
class McpStatsTest {

    private MCPGuards guards;

    @BeforeEach
    void setUp() {
        guards = new MCPGuards();
    }

    @Test
    void testMetricsSnapshotFields() {
        MCPGuards.MCPMetricsSnapshot snapshot = guards.getSnapshot();

        // 验证所有字段都存在
        assertThat(snapshot.calls()).isEqualTo(0);
        assertThat(snapshot.successes()).isEqualTo(0);
        assertThat(snapshot.failures()).isEqualTo(0);
        assertThat(snapshot.cacheHits()).isEqualTo(0);
        assertThat(snapshot.circuitOpenCount()).isEqualTo(0);
        assertThat(snapshot.avgDurationMs()).isEqualTo(0.0);
    }

    @Test
    void testMetricsAfterCall() {
        // 模拟成功调用
        guards.executeWithGuards("test_tool", () ->
            CompletableFuture.completedFuture(Map.of("result", "success"))
        );

        MCPGuards.MCPMetricsSnapshot snapshot = guards.getSnapshot();
        assertThat(snapshot.calls()).isGreaterThanOrEqualTo(1);
        assertThat(snapshot.successes()).isGreaterThanOrEqualTo(1);
    }

    @Test
    void testMetricsAfterFailure() {
        // 模拟失败调用
        guards.executeWithGuards("test_tool_fail", () ->
            CompletableFuture.failedFuture(new RuntimeException("test error"))
        );

        MCPGuards.MCPMetricsSnapshot snapshot = guards.getSnapshot();
        assertThat(snapshot.calls()).isGreaterThanOrEqualTo(1);
        assertThat(snapshot.failures()).isGreaterThanOrEqualTo(1);
    }
}
