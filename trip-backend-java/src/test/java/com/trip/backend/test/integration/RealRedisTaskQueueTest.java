package com.trip.backend.test.integration;

import com.trip.backend.infra.task.DegradedTaskRunner;
import com.trip.backend.infra.task.RetryPolicy;
import com.trip.backend.infra.task.TaskQueue;
import com.trip.backend.infra.task.TaskRegistry;
import com.trip.backend.infra.task.WorkerScheduler;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 真实环境集成测试（需本机 Docker Redis：localhost:6379）。
 *
 * 补跑 J-C0 Redis 后端判定：
 * - enqueue → LPUSH arq:queue:{name} → WorkerScheduler BRPOP 消费 → SETEX arq:result:{jobId}
 * - SETNX 幂等：同 job_id 重复入队只执行一次
 *
 * 测试写入唯一前缀 key，结束清理；Redis 不可达时跳过。
 */
class RealRedisTaskQueueTest {

    private static StringRedisTemplate redis;
    private static final String PREFIX = "realit-" + System.nanoTime();
    private static final java.util.List<String> QUEUES = new java.util.concurrent.CopyOnWriteArrayList<>();

    @BeforeAll
    static void connect() {
        try {
            LettuceConnectionFactory factory = new LettuceConnectionFactory("localhost", 6379);
            factory.afterPropertiesSet();
            redis = new StringRedisTemplate(factory);
            redis.afterPropertiesSet();
            assertEquals("PONG", redis.getConnectionFactory().getConnection().ping(), "Redis 应可达");
        } catch (Exception e) {
            throw new org.opentest4j.TestAbortedException("Redis 不可达，跳过真实环境测试: " + e.getMessage());
        }
    }

    @AfterAll
    static void cleanup() {
        if (redis == null) {
            return;
        }
        // 清理本测试写入的 key（只删唯一前缀，不触碰其它数据）
        for (String queue : QUEUES) {
            redis.delete("arq:queue:" + queue);
        }
        java.util.Set<String> keys = redis.keys(PREFIX + ":*");
        if (keys != null && !keys.isEmpty()) {
            redis.delete(keys);
        }
    }

    private TaskQueue newTaskQueue(TaskRegistry registry) {
        RetryPolicy policy = new RetryPolicy();
        DegradedTaskRunner runner = new DegradedTaskRunner(registry, policy);
        WorkerScheduler scheduler = new WorkerScheduler(registry, policy, redis);
        return new TaskQueue(redis, registry, runner, scheduler);
    }

    @Test
    void redisBackendExecutesTaskAndStoresResult() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        CountDownLatch executed = new CountDownLatch(1);
        String taskName = PREFIX + "-echo";
        QUEUES.add(taskName);
        registry.register(taskName, args -> {
            executed.countDown();
            return Map.of("echo", args.get("msg"));
        });

        TaskQueue queue = newTaskQueue(registry);
        String jobId = PREFIX + "-job-echo";
        queue.enqueue(taskName, Map.of("msg", "hello-redis"), jobId);

        assertTrue(executed.await(10, TimeUnit.SECONDS), "WorkerScheduler 应 BRPOP 消费并执行");
        // 结果 SETEX 在 handler 返回之后，轮询等待 arq:result:{jobId}
        String result = null;
        long deadline = System.currentTimeMillis() + 5000;
        while (result == null && System.currentTimeMillis() < deadline) {
            result = redis.opsForValue().get("arq:result:" + jobId);
            if (result == null) {
                Thread.sleep(50);
            }
        }
        assertTrue(result != null && result.contains("hello-redis"), "结果应写入 Redis: " + result);
        Object parsed = queue.getResult(jobId).orElseThrow();
        assertTrue(parsed instanceof Map<?, ?> && "hello-redis".equals(((Map<?, ?>) parsed).get("echo")),
            "getResult 应读到 Redis 结果（JSON 解析后）: " + parsed);
    }

    @Test
    void redisBackendSameJobIdEnqueuedTwiceExecutesOnce() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        AtomicInteger count = new AtomicInteger();
        CountDownLatch executed = new CountDownLatch(1);
        String taskName = PREFIX + "-dedup";
        QUEUES.add(taskName);
        registry.register(taskName, args -> {
            count.incrementAndGet();
            executed.countDown();
            return Map.of("ok", true);
        });

        TaskQueue queue = newTaskQueue(registry);
        String jobId = PREFIX + "-job-dedup";
        String first = queue.enqueue(taskName, Map.of(), jobId);
        String second = queue.enqueue(taskName, Map.of(), jobId);

        assertEquals(first, second, "同 job_id 返回相同 jobId");
        assertTrue(executed.await(10, TimeUnit.SECONDS), "任务应执行");
        Thread.sleep(500); // 等待潜在的重复执行窗口
        assertEquals(1, count.get(), "Redis SETNX 幂等：同 job_id 只执行一次");
        // 幂等键在 Redis 中
        assertTrue(Boolean.TRUE.equals(redis.hasKey("arq:job:" + jobId)), "SETNX 幂等键应存在");
    }

    @Test
    void redisBackendResultTtlIs3600() {
        // 结果 TTL 对齐 arq 语义（SETEX 3600）
        TaskQueue queue = newTaskQueue(new TaskRegistry());
        assertEquals(3600, TaskQueue.RESULT_TTL_SECONDS);
        assertEquals(3600, WorkerScheduler.RESULT_TTL_SECONDS);
    }
}
