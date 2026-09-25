package com.trip.backend.web.controller;

import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;
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

    private final DataSource dataSource;
    private final RedisConnectionFactory redisConnectionFactory;

    public HealthController(DataSource dataSource, RedisConnectionFactory redisConnectionFactory) {
        this.dataSource = dataSource;
        this.redisConnectionFactory = redisConnectionFactory;
    }

    /**
     * GET /health - 返回 PlainText "OK"（存活探针，依赖挂了也返回 200）
     */
    @GetMapping(value = "/health", produces = "text/plain")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("OK");
    }

    /**
     * GET /health/detail - 返回详细健康状态 JSON（含 DB/Redis checks）
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
        status.put("memory", Map.of("rss", heapUsage.getUsed()));

        // 真实 DB / Redis 检查（失败标 DOWN 但不抛异常，保证 detail 端点可用）
        Map<String, Object> checks = new HashMap<>();
        checks.put("db", checkDb());
        checks.put("redis", checkRedis());
        status.put("checks", checks);

        return ResponseEntity.ok(status);
    }

    private Map<String, Object> checkDb() {
        long t0 = System.currentTimeMillis();
        try (var conn = dataSource.getConnection()) {
            boolean ok = conn.isValid(2);
            return Map.of("status", ok ? "UP" : "DOWN", "latencyMs", System.currentTimeMillis() - t0);
        } catch (Exception e) {
            return Map.of("status", "DOWN", "error", e.getClass().getSimpleName());
        }
    }

    private Map<String, Object> checkRedis() {
        long t0 = System.currentTimeMillis();
        try (var conn = redisConnectionFactory.getConnection()) {
            String pong = conn.ping();
            boolean up = pong != null && !pong.isBlank();
            return Map.of("status", up ? "UP" : "DOWN",
                    "latencyMs", System.currentTimeMillis() - t0, "pong", String.valueOf(pong));
        } catch (Exception e) {
            return Map.of("status", "DOWN", "error", e.getClass().getSimpleName());
        }
    }

    /**
     * GET /metrics - 由 Micrometer Actuator 自动暴露
     */
    @GetMapping("/metrics")
    public ResponseEntity<String> metrics() {
        return ResponseEntity.ok("Metrics available at /actuator/prometheus");
    }
}
