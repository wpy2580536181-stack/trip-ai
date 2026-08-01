package com.trip.backend.web.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

/**
 * 健康检查控制器（对应 Python /health、/health/detail、/metrics）
 */
@RestController
@RequestMapping
public class HealthController {

    private static final long START_TIME = System.currentTimeMillis();

    /**
     * GET /health - 返回 PlainText "OK"
     */
    @GetMapping(value = "/health", produces = "text/plain")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("OK");
    }

    /**
     * GET /health/detail - 返回详细健康状态 JSON
     */
    @GetMapping(value = "/health/detail", produces = "application/json")
    public ResponseEntity<Map<String, Object>> healthDetail() {
        Map<String, Object> status = new HashMap<>();
        status.put("status", "UP");
        status.put("timestamp", Instant.now().toString());

        // PID
        try {
            String jvmName = ManagementFactory.getRuntimeMXBean().getName();
            status.put("pid", jvmName.split("@")[0]);
        } catch (Exception e) {
            status.put("pid", "unknown");
        }

        // Uptime
        long uptimeSeconds = (System.currentTimeMillis() - START_TIME) / 1000;
        status.put("uptime", uptimeSeconds);

        // Memory RSS（近似值）
        MemoryMXBean memoryBean = ManagementFactory.getMemoryMXBean();
        MemoryUsage heapUsage = memoryBean.getHeapMemoryUsage();
        long usedMemory = heapUsage.getUsed();
        status.put("memory", Map.of(
            "rss", usedMemory
        ));

        // Checks（预留，后续可添加 DB/Redis 检查）
        Map<String, Object> checks = new HashMap<>();
        checks.put("db", Map.of("status", "UNKNOWN"));
        checks.put("redis", Map.of("status", "UNKNOWN"));
        status.put("checks", checks);

        return ResponseEntity.ok(status);
    }

    /**
     * GET /metrics - 由 Micrometer Actuator 自动暴露
     * 此端点仅作为占位，实际由 actuator prometheus endpoint 提供
     */
    @GetMapping("/metrics")
    public ResponseEntity<String> metrics() {
        return ResponseEntity.ok("Metrics available at /actuator/prometheus");
    }
}
