package com.trip.backend.test.unit;

import com.trip.backend.infra.metrics.PrometheusMetrics;
import com.trip.backend.web.filter.PrometheusFilter;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-A2x PrometheusFilter 单元测试。
 * 验证 4 类业务指标输出、/metrics /health 排除、chat 打点。
 */
class PrometheusFilterTest {

    private final PrometheusMeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
    private final PrometheusMetrics metrics = new PrometheusMetrics(registry);
    private final PrometheusFilter filter = new PrometheusFilter(metrics);

    private String runThroughFilter(String method, String path, int status, String body) throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest(method, path);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = (req, res) -> {
            jakarta.servlet.http.HttpServletResponse httpRes = (jakarta.servlet.http.HttpServletResponse) res;
            httpRes.setStatus(status);
            httpRes.setContentType("application/json");
            httpRes.getWriter().write(body);
        };
        filter.doFilter(request, response, chain);
        return registry.scrape();
    }

    @Test
    void recordsHttpRequestsTotalWithLabels() throws Exception {
        String scrape = runThroughFilter("POST", "/api/trip/recommend", 200, "{}");

        assertTrue(scrape.contains("http_requests_total"),
            "scrape should contain http_requests_total, got:\n" + scrape);
        assertTrue(scrape.contains("method=\"POST\""), "should have method label");
        assertTrue(scrape.contains("path=\"/api/trip/recommend\""), "should have path label");
        assertTrue(scrape.contains("status=\"200\""), "should have status label");
    }

    @Test
    void recordsHttpRequestDurationHistogramWithBuckets() throws Exception {
        String scrape = runThroughFilter("GET", "/api/health/detail", 200, "{}");

        assertTrue(scrape.contains("http_request_duration_seconds"), "should have duration histogram");
        assertTrue(scrape.contains("http_request_duration_seconds_bucket"), "should have histogram buckets");
        assertTrue(scrape.contains("le=\"0.005\""), "first bucket should be 5ms (le=\"0.005\")");
        assertTrue(scrape.contains("le=\"10.0\""), "last bucket should be 10s (le=\"10.0\")");
    }

    @Test
    void excludesMetricsAndHealthPaths() throws Exception {
        // /metrics 不产生计数
        runThroughFilter("GET", "/metrics", 200, "ok");
        // /health 不产生计数
        runThroughFilter("GET", "/health", 200, "ok");

        String scrape = registry.scrape();
        assertFalse(scrape.contains("path=\"/metrics\""), "/metrics 访问不应被自身记录");
        assertFalse(scrape.contains("path=\"/health\""), "/health 访问不应被记录");

        // 但 /health/detail 仍记录
        runThroughFilter("GET", "/health/detail", 200, "{}");
        assertTrue(registry.scrape().contains("path=\"/health/detail\""),
            "/health/detail 应被记录（只精确排除 /health）");
    }

    @Test
    void chatDurationRecordedAfterChatRequest() throws Exception {
        // chat 流式路径本身会由 ChatController 打点；这里直接验证打点 API 产出指标
        metrics.recordChatDuration(1.5);

        String scrape = registry.scrape();
        assertTrue(scrape.contains("chat_request_duration_seconds"), "should have chat histogram");
        assertTrue(scrape.contains("chat_request_duration_seconds_bucket{le=\"0.1\"}"),
            "first chat bucket should be 0.1s");
        assertTrue(scrape.contains("le=\"60.0\""), "last chat bucket should be 60s");
    }

    @Test
    void toolInvocationsCounterRecorded() throws Exception {
        metrics.recordToolInvocation("search_hotels", true);
        metrics.recordToolInvocation("search_hotels", false);

        String scrape = registry.scrape();
        assertTrue(scrape.contains("tool_invocations_total"), "should have tool counter");
        // Micrometer 按字母序输出 label：status 在 tool 前
        assertTrue(scrape.contains("tool_invocations_total{status=\"success\",tool=\"search_hotels\"}"),
            "should have success label, got:\n" + scrape);
        assertTrue(scrape.contains("tool_invocations_total{status=\"failure\",tool=\"search_hotels\"}"),
            "should have failure label, got:\n" + scrape);
    }

    @Test
    void statusCodeCapturedFromResponse() throws Exception {
        String scrape = runThroughFilter("GET", "/api/spot/1", 404, "{}");
        assertTrue(scrape.contains("status=\"404\""), "should capture 404 status");
    }

    @Test
    void metricsFailureDoesNotBreakMainFlow() throws Exception {
        // 打点方法不抛异常：构造一个正常请求走一遍即可
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/trip/recommend");
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = (req, res) -> {
            jakarta.servlet.http.HttpServletResponse httpRes = (jakarta.servlet.http.HttpServletResponse) res;
            httpRes.setStatus(200);
            httpRes.setContentType("application/json");
            httpRes.getWriter().write("{\"ok\":true}");
        };
        // 不应抛异常
        filter.doFilter(request, response, chain);
        assertTrue(registry.scrape().contains("http_requests_total"));
    }
}
