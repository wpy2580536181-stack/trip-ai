package com.trip.backend.infra.task;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * 内存降级任务执行器（对应 Python TaskQueue 的 asyncio.create_task 降级路径）。
 *
 * - Redis 不可用时由 {@link TaskQueue} 转入本执行器
 * - Java 21 虚拟线程池执行（等价 Python asyncio，无需 Spring @Async）
 * - 失败重试：max_tries=3，退避 1/2/4s；单次执行超时 job_timeout=300s
 * - 结果内存缓存 TTL 3600s（对齐 arq 结果 SETEX 3600）
 * - 任务异常绝不静默：记录日志 + 结果标记 error
 */
@Component
public class DegradedTaskRunner {

    private static final Logger log = LoggerFactory.getLogger(DegradedTaskRunner.class);

    public static final long RESULT_TTL_SECONDS = 3600;

    private final TaskRegistry registry;
    private final RetryPolicy retryPolicy;
    private final ExecutorService executor;
    private final Map<String, CachedResult> results = new ConcurrentHashMap<>();

    public DegradedTaskRunner(TaskRegistry registry) {
        this(registry, new RetryPolicy());
    }

    @Autowired
    public DegradedTaskRunner(TaskRegistry registry, RetryPolicy retryPolicy) {
        this.registry = registry;
        this.retryPolicy = retryPolicy;
        this.executor = Executors.newVirtualThreadPerTaskExecutor();
    }

    /** 入队执行（异步，立即返回；失败重试/退避在后台线程进行）。 */
    public void submit(String taskName, Map<String, Object> args, String jobId) {
        executor.submit(() -> runWithRetry(taskName, args, jobId));
    }

    /** 读取任务结果（惰性 TTL 过期，对齐 Python MemoryIdempotencyStore 语义）。 */
    public Optional<Object> getResult(String jobId) {
        CachedResult entry = results.get(jobId);
        if (entry == null) {
            return Optional.empty();
        }
        if (System.currentTimeMillis() - entry.createdAtMillis() >= RESULT_TTL_SECONDS * 1000L) {
            results.remove(jobId, entry);
            return Optional.empty();
        }
        return Optional.ofNullable(entry.value());
    }

    void runWithRetry(String taskName, Map<String, Object> args, String jobId) {
        for (int attempt = 1; attempt <= retryPolicy.getMaxTries(); attempt++) {
            try {
                TaskHandler handler = registry.get(taskName)
                    .orElseThrow(() -> new IllegalStateException("task not registered: " + taskName));
                Map<String, Object> result = executeWithTimeout(handler, args);
                results.put(jobId, CachedResult.success(result, System.currentTimeMillis()));
                log.info("degraded_task_done task={} job={} attempt={}", taskName, jobId, attempt);
                return;
            } catch (Exception e) {
                log.error("degraded_task_failed task={} job={} attempt={} error={}",
                    taskName, jobId, attempt, e.getMessage());
                if (attempt < retryPolicy.getMaxTries()) {
                    sleepQuietly(retryPolicy.delayForTry(attempt).toMillis());
                } else {
                    // 最终失败：结果标记 error（不静默）
                    results.put(jobId, CachedResult.error(e.getMessage(), System.currentTimeMillis()));
                }
            }
        }
    }

    private Map<String, Object> executeWithTimeout(TaskHandler handler, Map<String, Object> args) throws Exception {
        Future<Map<String, Object>> future = executor.submit(() -> handler.execute(args));
        try {
            return future.get(retryPolicy.getJobTimeout().toMillis(), TimeUnit.MILLISECONDS);
        } catch (TimeoutException te) {
            future.cancel(true);
            throw te;
        }
    }

    private void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
        }
    }

    /** 内存结果条目（TTL 由调用方检查）。 */
    record CachedResult(Object value, String error, long createdAtMillis) {
        static CachedResult success(Object value, long createdAtMillis) {
            return new CachedResult(value, null, createdAtMillis);
        }

        static CachedResult error(String message, long createdAtMillis) {
            return new CachedResult(Map.of("error", message == null ? "unknown" : message), message, createdAtMillis);
        }
    }
}
