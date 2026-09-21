package com.trip.backend.test.unit;

import com.trip.backend.infra.task.DegradedTaskRunner;
import com.trip.backend.infra.task.RetryPolicy;
import com.trip.backend.infra.task.TaskQueue;
import com.trip.backend.infra.task.TaskRegistry;
import com.trip.backend.infra.task.WorkerScheduler;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C0 TaskQueue 双后端单元测试。
 *
 * 用指向不存在端口的真实 Lettuce 连接模拟 Redis 不可用（本机 JDK26 下 Mockito 不可用，
 * 且这样更贴近真实降级路径：Redis 操作抛异常 → 内存执行）。
 *
 * 合格判定：
 * 1. 同 job_id 重复入队只执行一次
 * 2. 失败退避时序 1s→2s→4s
 * 3. 结果 TTL = 3600s
 * 4. 断开 Redis 后任务仍在内存执行成功
 */
class TaskQueueTest {

    /** 构造一个指向不可用端口（6399 无服务）的 StringRedisTemplate。 */
    private StringRedisTemplate unavailableRedis() {
        LettuceConnectionFactory factory = new LettuceConnectionFactory("localhost", 6399);
        factory.afterPropertiesSet();
        StringRedisTemplate template = new StringRedisTemplate(factory);
        template.afterPropertiesSet();
        return template;
    }

    private TaskQueue newTaskQueue(TaskRegistry registry) {
        RetryPolicy policy = new RetryPolicy();
        DegradedTaskRunner runner = new DegradedTaskRunner(registry, policy);
        WorkerScheduler scheduler = new WorkerScheduler(registry, policy, unavailableRedis());
        return new TaskQueue(unavailableRedis(), registry, runner, scheduler);
    }

    @Test
    void sameJobIdEnqueuedTwiceExecutesOnce() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        AtomicInteger count = new AtomicInteger();
        CountDownLatch executed = new CountDownLatch(1);
        registry.register("sync_embedding", args -> {
            count.incrementAndGet();
            executed.countDown();
            return Map.of("spot_id", args.get("spot_id"), "status", "ok");
        });

        TaskQueue queue = newTaskQueue(registry);

        String first = queue.enqueue("sync_embedding", Map.of("spot_id", 1), "embedding_sync:1");
        String second = queue.enqueue("sync_embedding", Map.of("spot_id", 1), "embedding_sync:1");

        assertNotNull(first);
        assertEquals(first, second, "重复入队返回相同 job_id");
        assertTrue(executed.await(3, TimeUnit.SECONDS), "任务应执行");
        Thread.sleep(300); // 给可能触发的第二次执行留窗口
        assertEquals(1, count.get(), "相同 job_id 重复入队只执行一次");
    }

    @Test
    void defaultRetryBackoffIs1s2s4s() {
        RetryPolicy policy = new RetryPolicy();
        assertEquals(3, policy.getMaxTries());
        assertEquals(
            List.of(Duration.ofSeconds(1), Duration.ofSeconds(2), Duration.ofSeconds(4)),
            policy.getBackoffDelays(),
            "默认退避序列应为 1s→2s→4s"
        );
        assertEquals(Duration.ofSeconds(1), policy.delayForTry(1));
        assertEquals(Duration.ofSeconds(2), policy.delayForTry(2));
        assertEquals(Duration.ofSeconds(4), policy.delayForTry(3));
    }

    @Test
    void failedTaskRetriesWithBackoffSequence() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        List<Long> timestamps = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch done = new CountDownLatch(3);
        registry.register("flaky", args -> {
            timestamps.add(System.nanoTime());
            done.countDown();
            if (timestamps.size() <= 2) {
                throw new RuntimeException("boom");
            }
            return Map.of("ok", true);
        });

        // 短退避版策略：100ms→200ms→400ms（保持 1:2:4 比例，避免单测等 7 秒）
        RetryPolicy shortPolicy = new RetryPolicy(
            3,
            List.of(Duration.ofMillis(100), Duration.ofMillis(200), Duration.ofMillis(400)),
            Duration.ofSeconds(300)
        );
        DegradedTaskRunner runner = new DegradedTaskRunner(registry, shortPolicy);
        runner.submit("flaky", Map.of(), "j-flaky");

        assertTrue(done.await(5, TimeUnit.SECONDS), "三次尝试应全部完成");
        assertEquals(3, timestamps.size(), "失败应重试 2 次，共 3 次尝试");

        long d1 = timestamps.get(1) - timestamps.get(0);
        long d2 = timestamps.get(2) - timestamps.get(1);
        assertTrue(d1 >= 80_000_000L && d1 <= 250_000_000L,
            "第 1 次退避应约 100ms，实际 " + d1 / 1_000_000 + "ms");
        assertTrue(d2 >= 180_000_000L && d2 <= 450_000_000L,
            "第 2 次退避应约 200ms（2 倍），实际 " + d2 / 1_000_000 + "ms");

        // 最终成功结果可读
        Object result = runner.getResult("j-flaky").orElseThrow();
        assertEquals(Map.of("ok", true), result);
    }

    @Test
    void resultTtlIs3600Seconds() {
        assertEquals(3600, TaskQueue.RESULT_TTL_SECONDS, "TaskQueue 结果 TTL 应为 3600s");
        assertEquals(3600, DegradedTaskRunner.RESULT_TTL_SECONDS, "内存结果 TTL 应为 3600s");
        assertEquals(3600, WorkerScheduler.RESULT_TTL_SECONDS, "Redis 结果 TTL 应为 3600s");
        assertEquals(Duration.ofSeconds(300), new RetryPolicy().getJobTimeout(), "job_timeout 应为 300s");
    }

    @Test
    void redisUnavailableRunsTaskInMemorySuccessfully() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        CountDownLatch done = new CountDownLatch(1);
        registry.register("wiki_fetch", args -> {
            done.countDown();
            return Map.of("fetched", true, "url", args.get("url"));
        });

        TaskQueue queue = newTaskQueue(registry); // Redis 指向不可用端口

        String jobId = queue.enqueue("wiki_fetch", Map.of("url", "https://example.com"), "wf-1");
        assertNotNull(jobId);

        assertTrue(done.await(3, TimeUnit.SECONDS), "Redis 断开时任务应在内存执行");
        Object result = queue.getResult(jobId).orElseThrow(() -> new AssertionError("结果应存在"));
        assertTrue(result instanceof Map);
        assertEquals(true, ((Map<?, ?>) result).get("fetched"));
        assertEquals("https://example.com", ((Map<?, ?>) result).get("url"));
    }

    @Test
    void unregisteredTaskIsRejected() {
        TaskRegistry registry = new TaskRegistry();
        TaskQueue queue = newTaskQueue(registry);
        try {
            queue.enqueue("no_such_task", Map.of(), "x");
            throw new AssertionError("应拒绝未注册任务");
        } catch (IllegalArgumentException expected) {
            // expected
        }
    }
}
