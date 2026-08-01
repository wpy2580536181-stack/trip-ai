package com.trip.backend.web.filter;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

/**
 * Prometheus Filter（对应 Python prom_metrics.py）
 * 记录 4 类指标：
 * - http_requests_total{method,path,status}
 * - http_request_duration_seconds{method,path}（buckets 0.005–10s）
 * - chat_request_duration_seconds（buckets 0.1–60s，仅 /api/trip/chat）
 * - tool_invocations_total{tool,status}
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 1) // 在 RequestIdFilter 之后
public class PrometheusFilter extends OncePerRequestFilter {

    private final MeterRegistry meterRegistry;
    private final Counter.Builder httpRequestsTotalBuilder;
    private final Timer.Builder httpRequestDurationBuilder;
    private final Timer.Builder chatRequestDurationBuilder;

    public PrometheusFilter(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;

        // http_requests_total
        this.httpRequestsTotalBuilder = Counter.builder("http_requests_total")
            .description("Total HTTP requests")
            .tags("method", "unknown", "path", "unknown", "status", "unknown");

        // http_request_duration_seconds（0.005–10s buckets）
        this.httpRequestDurationBuilder = Timer.builder("http_request_duration_seconds")
            .description("HTTP request duration")
            .tags("method", "unknown", "path", "unknown")
            .publishPercentiles(0.5, 0.95, 0.99)
            .serviceLevelObjectives(
                java.time.Duration.ofMillis(5),
                java.time.Duration.ofMillis(10),
                java.time.Duration.ofMillis(50),
                java.time.Duration.ofMillis(100),
                java.time.Duration.ofMillis(500),
                java.time.Duration.ofSeconds(1),
                java.time.Duration.ofSeconds(5),
                java.time.Duration.ofSeconds(10)
            );

        // chat_request_duration_seconds（0.1–60s buckets，仅 chat 路径）
        this.chatRequestDurationBuilder = Timer.builder("chat_request_duration_seconds")
            .description("Chat request duration (SSE)")
            .tags("path", "/api/trip/chat")
            .publishPercentiles(0.5, 0.95, 0.99)
            .serviceLevelObjectives(
                java.time.Duration.ofMillis(100),
                java.time.Duration.ofMillis(500),
                java.time.Duration.ofSeconds(1),
                java.time.Duration.ofSeconds(5),
                java.time.Duration.ofSeconds(10),
                java.time.Duration.ofSeconds(15),
                java.time.Duration.ofSeconds(30),
                java.time.Duration.ofSeconds(60)
            );
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        long startTime = System.currentTimeMillis();
        String method = request.getMethod();
        String path = getPath(request);

        try {
            filterChain.doFilter(request, response);

            long durationMs = System.currentTimeMillis() - startTime;
            int status = response.getStatus();

            // 1. http_requests_total
            Counter.builder("http_requests_total")
                .tags("method", method, "path", path, "status", String.valueOf(status))
                .register(meterRegistry)
                .increment();

            // 2. http_request_duration_seconds
            Timer.builder("http_request_duration_seconds")
                .tags("method", method, "path", path)
                .register(meterRegistry)
                .record(durationMs, TimeUnit.MILLISECONDS);

            // 3. chat_request_duration_seconds（仅 /api/trip/chat）
            if (path.startsWith("/api/trip/chat")) {
                Timer.builder("chat_request_duration_seconds")
                    .tags("path", "/api/trip/chat")
                    .register(meterRegistry)
                    .record(durationMs, TimeUnit.MILLISECONDS);
            }

        } catch (IOException | ServletException e) {
            // 异常情况也记录
            Counter.builder("http_requests_total")
                .tags("method", method, "path", path, "status", "500")
                .register(meterRegistry)
                .increment();
            throw e;
        }
    }

    /**
     * 提取路径（排除查询参数）
     */
    private String getPath(HttpServletRequest request) {
        String uri = request.getRequestURI();
        // 标准化路径（移除多余斜杠）
        return uri.replaceAll("/{2,}", "/");
    }
}
