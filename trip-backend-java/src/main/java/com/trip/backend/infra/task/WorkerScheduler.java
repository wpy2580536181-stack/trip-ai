package com.trip.backend.infra.task;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * Redis 后端 Worker 调度器（对应 Python arq worker）。
 *
 * - 每个 taskName 一个常驻消费线程：BRPOP arq:queue:{name}（5s 轮询）
 * - 取到任务 → 执行（max_tries=3，退避 1/2/4s，job_timeout=300s）→
 *   SETEX arq:result:{jobId} 3600
 * - 懒启动（TaskQueue 在 Redis 可用时调用 ensureStarted），守护线程
 */
@Component
public class WorkerScheduler {

    private static final Logger log = LoggerFactory.getLogger(WorkerScheduler.class);

    public static final long RESULT_TTL_SECONDS = 3600;
    private static final long BRPOP_TIMEOUT_SECONDS = 5;
    private static final long RETRY_SLEEP_MS = 2000;

    private final TaskRegistry registry;
    private final RetryPolicy retryPolicy;
    private final StringRedisTemplate redisTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Map<String, Thread> workers = new ConcurrentHashMap<>();
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
    private volatile boolean running = true;

    public WorkerScheduler(TaskRegistry registry, RetryPolicy retryPolicy, StringRedisTemplate redisTemplate) {
        this.registry = registry;
        this.retryPolicy = retryPolicy;
        this.redisTemplate = redisTemplate;
    }

    /** 懒启动指定队列的消费线程（幂等）。 */
    public void ensureStarted(String taskName) {
        workers.computeIfAbsent(taskName, name -> {
            // 虚拟线程天然为 daemon，无需显式设置
            Thread thread = Thread.ofVirtual()
                .name("arq-worker-" + name)
                .start(() -> consumeLoop(name));
            log.info("worker_scheduler_started queue={}", name);
            return thread;
        });
    }

    private void consumeLoop(String taskName) {
        while (running) {
            try {
                String payload = redisTemplate.opsForList()
                    .rightPop("arq:queue:" + taskName, BRPOP_TIMEOUT_SECONDS, TimeUnit.SECONDS);
                if (payload == null) {
                    continue;
                }
                executePayload(payload);
            } catch (Exception e) {
                // Redis 暂时不可用：退避后继续轮询（worker 不退出）
                log.warn("worker_consume_failed queue={} error={}", taskName, e.getMessage());
                sleepQuietly(RETRY_SLEEP_MS);
            }
        }
    }

    /** 解析队列 payload 并执行（供单测直接调用，绕开消费循环）。 */
    public void executePayload(String payloadJson) throws Exception {
        Map<String, Object> payload = objectMapper.readValue(payloadJson, new TypeReference<>() {
        });
        String jobId = String.valueOf(payload.get("job_id"));
        String taskName = String.valueOf(payload.get("task"));
        @SuppressWarnings("unchecked")
        Map<String, Object> args = (Map<String, Object>) payload.get("args");
        runWithRetry(taskName, args, jobId);
    }

    void runWithRetry(String taskName, Map<String, Object> args, String jobId) {
        for (int attempt = 1; attempt <= retryPolicy.getMaxTries(); attempt++) {
            try {
                TaskHandler handler = registry.get(taskName)
                    .orElseThrow(() -> new IllegalStateException("task not registered: " + taskName));
                Map<String, Object> result = executeWithTimeout(handler, args);
                // 结果 SETEX arq:result:{jobId} 3600
                redisTemplate.opsForValue().set(
                    "arq:result:" + jobId,
                    objectMapper.writeValueAsString(result),
                    RESULT_TTL_SECONDS,
                    TimeUnit.SECONDS
                );
                log.info("worker_task_done task={} job={} attempt={}", taskName, jobId, attempt);
                return;
            } catch (Exception e) {
                log.error("worker_task_failed task={} job={} attempt={} error={}",
                    taskName, jobId, attempt, e.getMessage());
                if (attempt < retryPolicy.getMaxTries()) {
                    sleepQuietly(retryPolicy.delayForTry(attempt).toMillis());
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
}
