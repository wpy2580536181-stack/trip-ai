package com.trip.backend.service.mcp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * MCP 守卫集合（熔断器 + 限流器 + 缓存 + 指标）
 *
 * 对应 Python services/mcp/guards.py
 *
 * 功能：
 * - MCPCircuitBreaker：连续 5 次失败熔断，60s 半开试探
 * - MCPRateLimiter：令牌桶 3/s，capacity 5
 * - MCPCache：TTL 1800s，仅 maps_weather/maps_geo 可缓存
 * - MCPMetrics：calls/successes/failures/cache_hits/circuit_open_count/avg_duration_ms
 */
public class MCPGuards {

    private static final Logger log = LoggerFactory.getLogger(MCPGuards.class);

    // 可缓存工具名称
    private static final String[] CACHEABLE_TOOLS = {"maps_weather", "maps_geo"};

    private final MCPCircuitBreaker circuitBreaker;
    private final MCPRateLimiter rateLimiter;
    private final MCPCache cache;
    private final MCPMetrics metrics;

    public MCPGuards() {
        this.circuitBreaker = new MCPCircuitBreaker(5, 60);
        this.rateLimiter = new MCPRateLimiter(3.0, 5);
        this.cache = new MCPCache(1800);
        this.metrics = new MCPMetrics();
    }

    /**
     * 带 guards 执行工具调用
     *
     * @param toolName 工具名
     * @param supplier 调用逻辑
     * @return 工具结果
     */
    public CompletableFuture<Map<String, Object>> executeWithGuards(
            String toolName,
            java.util.function.Supplier<CompletableFuture<Map<String, Object>>> supplier) {

        // 1. 熔断器检查
        if (circuitBreaker.isOpen()) {
            log.warn("[MCPGuards] Circuit breaker open for tool: {}", toolName);
            metrics.recordCircuitOpen();
            return CompletableFuture.failedFuture(
                new IllegalStateException("MCP circuit breaker open, try again later")
            );
        }

        // 2. 限流器检查
        try {
            if (!rateLimiter.tryAcquire()) {
                log.warn("[MCPGuards] Rate limited for tool: {}", toolName);
                return CompletableFuture.failedFuture(
                    new IllegalStateException("MCP rate limited, please retry later")
                );
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(e);
        }

        // 3. 缓存检查（仅可缓存工具）
        if (isCacheable(toolName)) {
            Map<String, Object> cached = cache.get(toolName);
            if (cached != null) {
                log.debug("[MCPGuards] Cache hit for tool: {}", toolName);
                metrics.recordCacheHit();
                return CompletableFuture.completedFuture(cached);
            }
        }

        // 4. 执行调用
        return supplier.get().whenComplete((result, error) -> {
            if (error != null) {
                circuitBreaker.recordFailure();
                metrics.recordFailure();
            } else {
                circuitBreaker.recordSuccess();
                metrics.recordSuccess();

                // 缓存可缓存工具的结果
                if (isCacheable(toolName)) {
                    cache.set(toolName, result);
                }
            }
        });
    }

    /**
     * 记录指标
     */
    public void recordMetrics(String toolName, boolean success, long durationMs) {
        metrics.recordCall(toolName, success, durationMs);
    }

    /**
     * 获取指标快照
     */
    public MCPMetricsSnapshot getSnapshot() {
        return metrics.getSnapshot();
    }

    /**
     * 检查工具是否可缓存
     */
    private boolean isCacheable(String toolName) {
        for (String cacheable : CACHEABLE_TOOLS) {
            if (toolName.contains(cacheable)) {
                return true;
            }
        }
        return false;
    }

    // ==================== 内部类 ====================

    /**
     * MCP 熔断器
     */
    static class MCPCircuitBreaker {
        private static final int FAILURE_THRESHOLD = 5;
        private static final long RECOVERY_TIMEOUT_MS = 60_000;

        private int failureCount = 0;
        private long lastFailureTime = 0;
        private boolean open = false;

        public boolean isOpen() {
            if (open) {
                // 检查是否到恢复时间
                if (System.currentTimeMillis() - lastFailureTime >= RECOVERY_TIMEOUT_MS) {
                    open = false;
                    failureCount = 0;
                    log.info("[MCPCircuitBreaker] Half-open: allowing probe request");
                }
            }
            return open;
        }

        public void recordFailure() {
            failureCount++;
            lastFailureTime = System.currentTimeMillis();

            if (failureCount >= FAILURE_THRESHOLD && !open) {
                open = true;
                log.warn("[MCPCircuitBreaker] Opened after {} failures", failureCount);
            }
        }

        public void recordSuccess() {
            if (open) {
                open = false;
                failureCount = 0;
                log.info("[MCPCircuitBreaker] Closed (probe succeeded)");
            }
        }
    }

    /**
     * MCP 限流器（令牌桶）
     */
    static class MCPRateLimiter {
        private final double rate; // 令牌生成速率（个/秒）
        private final int capacity;
        private double tokens;
        private long lastRefillTime;

        public MCPRateLimiter(double rate, int capacity) {
            this.rate = rate;
            this.capacity = capacity;
            this.tokens = capacity;
            this.lastRefillTime = System.currentTimeMillis();
        }

        public synchronized boolean tryAcquire() throws InterruptedException {
            refill();

            if (tokens >= 1.0) {
                tokens -= 1.0;
                return true;
            }

            return false;
        }

        private void refill() {
            long now = System.currentTimeMillis();
            double elapsed = (now - lastRefillTime) / 1000.0;
            tokens = Math.min(capacity, tokens + elapsed * rate);
            lastRefillTime = now;
        }
    }

    /**
     * MCP 缓存（TTL 1800s）
     */
    static class MCPCache {
        private final long ttlMs;

        public MCPCache(long ttlMs) {
            this.ttlMs = ttlMs;
        }

        public Map<String, Object> get(String toolName) {
            // TODO: D6 实现后补充
            return null;
        }

        public void set(String toolName, Map<String, Object> result) {
            // TODO: D6 实现后补充
        }
    }

    /**
     * MCP 指标收集
     */
    static class MCPMetrics {
        private int calls = 0;
        private int successes = 0;
        private int failures = 0;
        private int cacheHits = 0;
        private int circuitOpenCount = 0;
        private double totalDurationMs = 0;
        private int durationSamples = 0;

        public synchronized void recordCall(String toolName, boolean success, long durationMs) {
            calls++;
            if (success) {
                successes++;
            } else {
                failures++;
            }
            totalDurationMs += durationMs;
            durationSamples++;
        }

        public synchronized void recordCacheHit() {
            cacheHits++;
        }

        public synchronized void recordCircuitOpen() {
            circuitOpenCount++;
        }

        public synchronized MCPMetricsSnapshot getSnapshot() {
            return new MCPMetricsSnapshot(
                calls,
                successes,
                failures,
                cacheHits,
                circuitOpenCount,
                durationSamples > 0 ? totalDurationMs / durationSamples : 0
            );
        }
    }

    /**
     * MCP 指标快照
     */
    public record MCPMetricsSnapshot(
        int calls,
        int successes,
        int failures,
        int cacheHits,
        int circuitOpenCount,
        double avgDurationMs
    ) {}
}
