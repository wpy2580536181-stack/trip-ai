package com.trip.backend.service.agent.tools;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

/**
 * 工具韧性包装器（对应 Python resilience.py ToolResilienceWrapper）。
 *
 * - 超时保护（future.get）
 * - 自动重试 + 退避：429 用 Retry-After（封顶 30s）；其余指数退避 2^attempt（封顶 10s）
 * - 熔断器（可选，按 tool 共享）
 * - 降级返回值（所有重试失败后返回 fallback，不抛异常给上层）
 */
public class ResilienceWrapper {

    private static final ExecutorService EXECUTOR = Executors.newThreadPerTaskExecutor(
        Thread.ofVirtual().name("tool-call-", 0).factory());

    private static final long RETRY_AFTER_CAP_SEC = 30;
    private static final long EXPONENTIAL_CAP_SEC = 10;

    private final long timeoutSec;
    private final int retries;
    private final String fallback;
    private final CircuitBreaker breaker; // 可空

    public ResilienceWrapper(long timeoutSec, int retries, String fallback, CircuitBreaker breaker) {
        this.timeoutSec = timeoutSec;
        this.retries = retries;
        this.fallback = fallback;
        this.breaker = breaker;
    }

    /** 可抛异常的函数式接口（工具 execute 声明 throws Exception）。 */
    @FunctionalInterface
    public interface ThrowingSupplier {
        String get() throws Exception;
    }

    /**
     * 执行工具；任何异常/超时/熔断都不抛出，返回 fallback 文案。
     */
    public String call(ThrowingSupplier fn) {
        if (breaker != null && !breaker.allowRequest()) {
            return fallback;
        }

        Exception lastError = null;
        for (int attempt = 0; attempt <= retries; attempt++) {
            try {
                String result = withTimeout(fn);
                if (breaker != null) {
                    breaker.recordSuccess();
                }
                return result;
            } catch (Exception e) {
                lastError = e;
                if (breaker != null) {
                    breaker.recordFailure();
                }
                if (attempt < retries) {
                    sleepQuietly(backoffSeconds(lastError, attempt));
                }
            }
        }
        return fallback;
    }

    /**
     * 退避秒数：429 优先 Retry-After（封顶 30s）；否则 2^attempt（封顶 10s）。
     */
    long backoffSeconds(Exception error, int attempt) {
        if (error instanceof RateLimitException rle) {
            return Math.min(rle.retryAfterSec(), RETRY_AFTER_CAP_SEC);
        }
        return Math.min((long) Math.pow(2, attempt), EXPONENTIAL_CAP_SEC);
    }

    private String withTimeout(ThrowingSupplier fn) {
        Future<String> future = EXECUTOR.submit(() -> {
            try {
                return fn.get();
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        });
        try {
            return future.get(timeoutSec, TimeUnit.SECONDS);
        } catch (java.util.concurrent.TimeoutException e) {
            future.cancel(true);
            throw new RuntimeException("tool call timed out after " + timeoutSec + "s", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("tool call interrupted", e);
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            if (cause instanceof RuntimeException re) {
                throw re;
            }
            throw new RuntimeException(cause);
        }
    }

    private void sleepQuietly(long seconds) {
        try {
            Thread.sleep(seconds * 1000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
