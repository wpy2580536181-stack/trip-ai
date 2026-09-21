package com.trip.backend.web.controller;

import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * /metrics 端点（对应 Python metrics_endpoint）
 *
 * 输出 Prometheus 文本格式，供 Prometheus 抓取。
 * 独立注册、不走 PrometheusFilter（Filter 已精确排除 /metrics，避免自激）。
 */
@RestController
public class MetricsController {

    public static final String CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8";

    private final PrometheusMeterRegistry registry;

    public MetricsController(PrometheusMeterRegistry registry) {
        this.registry = registry;
    }

    @GetMapping(value = "/metrics", produces = CONTENT_TYPE_LATEST)
    public String metrics() {
        return registry.scrape();
    }
}
