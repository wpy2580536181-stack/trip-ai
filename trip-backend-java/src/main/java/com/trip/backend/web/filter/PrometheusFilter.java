package com.trip.backend.web.filter;

import com.trip.backend.infra.metrics.PrometheusMetrics;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpServletResponseWrapper;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Set;

/**
 * Prometheus 指标 Filter（对应 Python src/middleware/prom_metrics.py）
 *
 * - http_requests_total{method,path,status} / http_request_duration_seconds{method,path} 自动打点
 * - 排除 /metrics、/health 精确路径（/health/detail 仍记录），避免自激
 * - 不缓冲响应体，兼容 SSE 流式接口
 * - metrics 记录失败不影响主流程
 *
 * 注册顺序见 FilterOrderConfig（order=2，RequestIdFilter 之后、GzipFilter 之前）。
 */
@Component
public class PrometheusFilter extends OncePerRequestFilter {

    private static final Set<String> EXCLUDE_PATHS = Set.of("/metrics", "/health");

    private final PrometheusMetrics metrics;

    public PrometheusFilter(PrometheusMetrics metrics) {
        this.metrics = metrics;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();
        String method = request.getMethod();

        if (path == null || method == null || EXCLUDE_PATHS.contains(path)) {
            filterChain.doFilter(request, response);
            return;
        }

        // 捕获真实状态码（默认 500，与 Python 一致：异常未捕获时兜底）
        final int[] statusHolder = {HttpServletResponse.SC_INTERNAL_SERVER_ERROR};
        HttpServletResponse statusCapturingResponse = new HttpServletResponseWrapper(response) {
            @Override
            public void setStatus(int sc) {
                statusHolder[0] = sc;
                super.setStatus(sc);
            }

            @Override
            public void sendError(int sc) throws IOException {
                statusHolder[0] = sc;
                super.sendError(sc);
            }

            @Override
            public void sendError(int sc, String msg) throws IOException {
                statusHolder[0] = sc;
                super.sendError(sc, msg);
            }
        };

        long startNanos = System.nanoTime();
        try {
            filterChain.doFilter(request, statusCapturingResponse);
        } finally {
            // 兜底：若链内未显式 setStatus（如容器默认 200），取 response.getStatus()
            int status = statusHolder[0];
            if (status == HttpServletResponse.SC_INTERNAL_SERVER_ERROR) {
                int resolved = response.getStatus();
                if (resolved > 0) {
                    status = resolved;
                }
            }
            try {
                double durationSeconds = (System.nanoTime() - startNanos) / 1_000_000_000.0;
                metrics.recordHttpRequest(method, path, status);
                metrics.recordHttpDuration(method, path, durationSeconds);
            } catch (Exception e) {
                // metrics 记录失败不影响主流程
                logger.warn("prom_metrics_record_failed: method=" + method + " path=" + path, e);
            }
        }
    }
}
