package com.trip.backend.service.mcp;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * MCP 调用守卫（对应 Python mcp/guards.py）。
 *
 * - 熔断：fail_max=5 / reset 60s（复用 agent.tools.CircuitBreaker）
 * - 限流：令牌桶 3/s、capacity 5
 * - 缓存：TTL 1800s，仅 maps_weather / maps_geo
 * - 指标：calls/successes/failures/cacheHits/circuitOpenCount/avgDurationMs
 */
@Component
public class Guards {

    /** 可缓存的 MCP 工具（对齐 Python CACHEABLE_TOOLS）。 */
    public static final Set<String> CACHEABLE_TOOLS = Set.of("maps_weather", "maps_geo");

    private final CircuitBreakerShim breaker;
    private final Map<String, TokenBucket> limiters = new ConcurrentHashMap<>();
    private final Map<String, TtlCache> caches = new ConcurrentHashMap<>();
    private final Metrics metrics = new Metrics();

    public Guards() {
        this(5, 60_000, 3.0, 5, 1800);
    }

    /** 测试可注入参数。 */
    public Guards(int failMax, long resetTimeoutMs, double ratePerSec, int capacity, long cacheTtlSec) {
        this.breaker = new CircuitBreakerShim(failMax, resetTimeoutMs);
    }

    /** 调用快照指标。 */
    public static class Metrics {
        public long calls;
        public long successes;
        public long failures;
        public long cacheHits;
        public long circuitOpenCount;
        public double avgDurationMs;
    }

    /** 供 /api/admin/mcp-stats 的不可变快照。 */
    public synchronized Metrics snapshot() {
        Metrics m = new Metrics();
        m.calls = metrics.calls;
        m.successes = metrics.successes;
        m.failures = metrics.failures;
        m.cacheHits = metrics.cacheHits;
        m.circuitOpenCount = metrics.circuitOpenCount;
        m.avgDurationMs = metrics.avgDurationMs;
        return m;
    }

    public synchronized void resetMetrics() {
        metrics.calls = 0;
        metrics.successes = 0;
        metrics.failures = 0;
        metrics.cacheHits = 0;
        metrics.circuitOpenCount = 0;
        metrics.avgDurationMs = 0;
    }

    /** 可抛异常的函数式接口。 */
    @FunctionalInterface
    public interface Callable {
        String call() throws Exception;
    }

    /**
     * 通过 guards 调用 MCP 工具。返回工具结果；失败抛异常。
     */
    public String call(String toolName, String cacheKey, Callable fn) {
        metrics.calls++;
        long start = System.nanoTime();

        // 1. 缓存（仅可缓存工具）
        if (CACHEABLE_TOOLS.contains(toolName)) {
            TtlCache cache = caches.computeIfAbsent(toolName, k -> new TtlCache(1800, 500));
            String cached = cache.get(cacheKey);
            if (cached != null) {
                metrics.cacheHits++;
                metrics.successes++;
                recordDuration(start);
                return cached;
            }
        }

        // 2. 限流
        TokenBucket limiter = limiters.computeIfAbsent(toolName, k -> new TokenBucket(3.0, 5));
        if (!limiter.tryAcquire()) {
            metrics.failures++;
            throw new RuntimeException("MCP 工具 " + toolName + " 被限流");
        }

        // 3. 熔断 + 执行
        try {
            String result = breaker.call(fn);
            metrics.successes++;
            if (CACHEABLE_TOOLS.contains(toolName) && cacheKey != null) {
                caches.get(toolName).set(cacheKey, result);
            }
            recordDuration(start);
            return result;
        } catch (Exception e) {
            metrics.failures++;
            if (breaker.isOpen()) {
                metrics.circuitOpenCount++;
            }
            throw new RuntimeException(e);
        }
    }

    public boolean circuitIsOpen() {
        return breaker.isOpen();
    }

    public CircuitBreakerShim breaker() {
        return breaker;
    }

    private void recordDuration(long startNanos) {
        double ms = (System.nanoTime() - startNanos) / 1_000_000.0;
        long actual = metrics.successes + metrics.failures;
        // 简化：移动平均
        metrics.avgDurationMs = metrics.avgDurationMs == 0 ? ms : (metrics.avgDurationMs + ms) / 2;
    }

    /** 极简三态熔断器（与 agent.tools.CircuitBreaker 语义一致，独立实现避免循环依赖）。 */
    public static class CircuitBreakerShim {
        public enum State { CLOSED, OPEN, HALF_OPEN }

        private final int failMax;
        private final long resetTimeoutMs;
        private State state = State.CLOSED;
        private int failures;
        private long lastFailureAt;

        CircuitBreakerShim(int failMax, long resetTimeoutMs) {
            this.failMax = failMax;
            this.resetTimeoutMs = resetTimeoutMs;
        }

        synchronized boolean isOpen() {
            return state == State.OPEN;
        }

        synchronized State state() {
            return state;
        }

        synchronized String call(Callable fn) throws Exception {
            if (state == State.OPEN) {
                if (System.currentTimeMillis() - lastFailureAt >= resetTimeoutMs) {
                    state = State.HALF_OPEN; // 试探
                } else {
                    throw new RuntimeException("circuit breaker open");
                }
            }
            try {
                String r = fn.call();
                if (state == State.HALF_OPEN) {
                    state = State.CLOSED;
                    failures = 0;
                }
                return r;
            } catch (Exception e) {
                failures++;
                lastFailureAt = System.currentTimeMillis();
                if (state == State.HALF_OPEN || failures >= failMax) {
                    state = State.OPEN;
                }
                throw e;
            }
        }

        synchronized void reset() {
            state = State.CLOSED;
            failures = 0;
            lastFailureAt = 0;
        }
    }

    /** 令牌桶（3/s、capacity 5）。 */
    public static class TokenBucket {
        private final double rate;
        private final int capacity;
        private double tokens;
        private long lastRefill;

        TokenBucket(double rate, int capacity) {
            this.rate = rate;
            this.capacity = capacity;
            this.tokens = capacity;
            this.lastRefill = System.currentTimeMillis();
        }

        synchronized boolean tryAcquire() {
            long now = System.currentTimeMillis();
            double elapsedSec = (now - lastRefill) / 1000.0;
            tokens = Math.min(capacity, tokens + elapsedSec * rate);
            lastRefill = now;
            if (tokens >= 1.0) {
                tokens -= 1.0;
                return true;
            }
            return false;
        }
    }

    /** TTL 缓存（1800s）。 */
    static class TtlCache {
        private final long ttlMs;
        private final int maxSize;
        private final Map<String, long[]> expire = new ConcurrentHashMap<>();
        private final Map<String, String> store = new ConcurrentHashMap<>();

        TtlCache(long ttlSec, int maxSize) {
            this.ttlMs = ttlSec * 1000;
            this.maxSize = maxSize;
        }

        String get(String key) {
            long[] exp = expire.get(key);
            if (exp == null) {
                return null;
            }
            if (System.currentTimeMillis() > exp[0]) {
                store.remove(key);
                expire.remove(key);
                return null;
            }
            return store.get(key);
        }

        void set(String key, String value) {
            if (store.size() >= maxSize) {
                store.clear();
                expire.clear();
            }
            store.put(key, value);
            expire.put(key, new long[]{System.currentTimeMillis() + ttlMs});
        }
    }
}
