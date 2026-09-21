package com.trip.backend.infra.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

import java.time.Duration;

/**
 * 业务指标采集（对应 Python src/middleware/prom_metrics.py）
 *
 * 4 类核心指标：
 * 1. http_requests_total{method,path,status}    Counter（PrometheusFilter 打点）
 * 2. http_request_duration_seconds{method,path} Histogram（PrometheusFilter 打点，buckets 5ms~10s）
 * 3. chat_request_duration_seconds              Histogram（ChatController 流收尾打点，buckets 0.1s~60s）
 * 4. tool_invocations_total{tool,status}        Counter（D5 工具层接入时打点）
 *
 * Micrometer → Prometheus 命名约定：Timer 自动追加 _seconds，Counter 保留原名，
 * 因此 meter 名使用 *.total / *.duration，输出与 Python 指标名逐一对齐。
 */
@Component
public class PrometheusMetrics {

    /** http_request_duration_seconds buckets：5ms ~ 10s（与 Python 一致） */
    private static final Duration[] HTTP_DURATION_SLO = {
        Duration.ofMillis(5), Duration.ofMillis(10), Duration.ofMillis(25),
        Duration.ofMillis(50), Duration.ofMillis(100), Duration.ofMillis(250),
        Duration.ofMillis(500), Duration.ofSeconds(1), Duration.ofMillis(2500),
        Duration.ofSeconds(5), Duration.ofSeconds(10)
    };

    /** chat_request_duration_seconds buckets：0.1s ~ 60s（与 Python 一致） */
    private static final Duration[] CHAT_DURATION_SLO = {
        Duration.ofMillis(100), Duration.ofMillis(500), Duration.ofSeconds(1),
        Duration.ofSeconds(2), Duration.ofSeconds(5), Duration.ofSeconds(10),
        Duration.ofSeconds(30), Duration.ofSeconds(60)
    };

    private final MeterRegistry registry;
    private final Timer chatRequestDuration;

    public PrometheusMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.chatRequestDuration = Timer.builder("chat.request.duration")
            .description("Chat stream request duration in seconds")
            .serviceLevelObjectives(CHAT_DURATION_SLO)
            .register(registry);
    }

    /** HTTP 请求计数（PrometheusFilter 调用）。 */
    public void recordHttpRequest(String method, String path, int status) {
        registry.counter("http.requests.total",
            "method", method, "path", path, "status", String.valueOf(status)).increment();
    }

    /** HTTP 请求时长（PrometheusFilter 调用）。 */
    public void recordHttpDuration(String method, String path, double seconds) {
        httpRequestDuration(method, path).record(Duration.ofNanos((long) (seconds * 1_000_000_000L)));
    }

    /** chat 流式响应总耗时（ChatController 流收尾调用，对应 Python record_chat_duration）。 */
    public void recordChatDuration(double seconds) {
        chatRequestDuration.record(Duration.ofNanos((long) (seconds * 1_000_000_000L)));
    }

    /** agent tool 调用结果（D5 工具层接入，对应 Python record_tool_invocation）。 */
    public void recordToolInvocation(String tool, boolean success) {
        registry.counter("tool.invocations.total",
            "tool", tool, "status", success ? "success" : "failure").increment();
    }

    private Timer httpRequestDuration(String method, String path) {
        return Timer.builder("http.request.duration")
            .description("HTTP request duration in seconds")
            .serviceLevelObjectives(HTTP_DURATION_SLO)
            .tags("method", method, "path", path)
            .register(registry);
    }
}
