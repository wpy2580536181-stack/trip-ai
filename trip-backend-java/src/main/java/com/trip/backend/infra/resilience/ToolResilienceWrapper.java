package com.trip.backend.infra.resilience;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import java.util.function.Supplier;

/**
 * 工具韧性包装器
 *
 * 对应 Python resilience.py::ToolResilienceWrapper
 *
 * 功能：
 * - 超时保护
 * - 自动重试（指数退避）
 * - 熔断器
 * - 降级返回值
 *
 * 设计：熔断与降级解耦
 * - 熔断（circuitBreaker）：决定是否调下游
 * - 降级（fallback）：下游失败时返回什么默认值
 */
public class ToolResilienceWrapper {

    private static final Logger log = LoggerFactory.getLogger(ToolResilienceWrapper.class);

    private final long timeoutMs;
    private final int maxRetries;
    private final String fallback;
    private final CircuitBreaker circuitBreaker;

    public ToolResilienceWrapper(
            long timeoutMs,
            int maxRetries,
            String fallback,
            CircuitBreaker circuitBreaker) {
        this.timeoutMs = timeoutMs;
        this.maxRetries = maxRetries;
        this.fallback = fallback;
        this.circuitBreaker = circuitBreaker;
    }

    /**
     * 执行工具调用（同步版）
     *
     * @param callable 工具调用
     * @return 工具结果
     */
    public String execute(Callable<String> callable) throws Exception {
        return execute(callable, 0);
    }

    /**
     * 执行工具调用（内部递归）
     */
    private String execute(Callable<String> callable, int attempt) throws Exception {
        // 1. 熔断器检查
        if (circuitBreaker != null && !circuitBreaker.allowRequest()) {
            log.warn("[Resilience] Circuit breaker open: {}, returning fallback", circuitBreaker.getName());
            return fallback;
        }

        // 2. 超时控制
        CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
            try {
                return callable.call();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });

        String result;
        try {
            result = future.get(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (java.util.concurrent.TimeoutException e) {
            future.cancel(true);
            log.warn("[Resilience] Timeout after {}ms (attempt {}/{})", timeoutMs, attempt + 1, maxRetries + 1);

            if (attempt < maxRetries) {
                // 指数退避：2^attempt * 1000ms，封顶 10000ms
                long backoff = Math.min((long) Math.pow(2, attempt) * 1000, 10000);
                log.info("[Resilience] Retrying in {}ms...", backoff);
                Thread.sleep(backoff);
                return execute(callable, attempt + 1);
            }

            // 重试耗尽
            if (circuitBreaker != null) {
                circuitBreaker.recordFailure();
            }
            log.error("[Resilience] All {} retries exhausted", maxRetries + 1);
            return fallback;
        } catch (Exception e) {
            log.warn("[Resilience] Exception: {} (attempt {}/{})", e.getMessage(), attempt + 1, maxRetries + 1);

            if (attempt < maxRetries) {
                // 429 错误：Retry-After 优先
                long retryAfter = extractRetryAfter(e);
                if (retryAfter > 0) {
                    log.info("[Resilience] 429 error, retry after {}ms", retryAfter);
                    Thread.sleep(Math.min(retryAfter, 30000)); // 封顶 30s
                } else {
                    // 指数退避
                    long backoff = Math.min((long) Math.pow(2, attempt) * 1000, 10000);
                    Thread.sleep(backoff);
                }
                return execute(callable, attempt + 1);
            }

            // 重试耗尽
            if (circuitBreaker != null) {
                circuitBreaker.recordFailure();
            }
            return fallback;
        }

        // 成功
        if (circuitBreaker != null) {
            circuitBreaker.recordSuccess();
        }
        return result;
    }

    /**
     * 从异常提取 Retry-After（秒或毫秒）
     */
    private long extractRetryAfter(Exception e) {
        String msg = e.getMessage();
        if (msg == null) {
            return 0;
        }

        // 简单提取 "retry after Xs" 或 "retry-after: X"
        try {
            if (msg.contains("429") || msg.contains("Too Many Requests")) {
                // 尝试提取秒数
                java.util.regex.Pattern pattern = java.util.regex.Pattern.compile(
                    "(?:retry.after|Retry-After)[:\\s]+(\\d+)",
                    java.util.regex.Pattern.CASE_INSENSITIVE
                );
                java.util.regex.Matcher matcher = pattern.matcher(msg);
                if (matcher.find()) {
                    long seconds = Long.parseLong(matcher.group(1));
                    return seconds * 1000; // 转换为毫秒
                }
            }
        } catch (Exception ex) {
            // 忽略提取失败
        }

        return 0;
    }

    /**
     * 创建 Builder
     */
    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private long timeoutMs = 10_000;
        private int maxRetries = 2;
        private String fallback = "";
        private CircuitBreaker circuitBreaker;

        public Builder timeout(long timeoutMs) {
            this.timeoutMs = timeoutMs;
            return this;
        }

        public Builder retries(int maxRetries) {
            this.maxRetries = maxRetries;
            return this;
        }

        public Builder fallback(String fallback) {
            this.fallback = fallback;
            return this;
        }

        public Builder circuitBreaker(CircuitBreaker circuitBreaker) {
            this.circuitBreaker = circuitBreaker;
            return this;
        }

        public ToolResilienceWrapper build() {
            return new ToolResilienceWrapper(timeoutMs, maxRetries, fallback, circuitBreaker);
        }
    }
}
