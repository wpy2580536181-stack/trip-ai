package com.trip.backend.test.unit;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import com.trip.backend.infra.task.DegradedTaskRunner;
import com.trip.backend.infra.task.RetryPolicy;
import com.trip.backend.infra.task.TaskQueue;
import com.trip.backend.infra.task.TaskRegistry;
import com.trip.backend.infra.task.WorkerScheduler;
import com.trip.backend.service.rag.VectorSearchSpots;
import com.trip.backend.task.EmbeddingSyncTask;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C4 EmbeddingSyncTask 单元测试。
 *
 * - 注册：taskName="embedding_sync" 挂载到 TaskRegistry
 * - job_id = embedding_sync:{spotId}（幂等，重复入队只执行一次）
 * - worker 文档文本 = city name description tags_str category（对齐 Python f-string）
 * - embedding 不可用 → 抛异常 → 退避重试（max_tries=3，由队列层执行）
 *
 * [需真实环境]：判定 1（create/update/bulk 后 spots.embedding 非空且余弦≈1）需
 * PostgreSQL（pgvector）+ ONNX 模型，本机不可执行；SQL 更新成功路径待真实环境验证。
 */
class EmbeddingSyncTaskTest {

    /** 指向不可用端口（6399）的 StringRedisTemplate，触发内存降级执行。 */
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

    /** 假 embedder：记录收到的文本，返回固定向量（不依赖 ONNX 模型）。 */
    static class FakeEmbedder extends BgeEmbedder {
        final AtomicReference<String> lastText = new AtomicReference<>();

        FakeEmbedder() {
            super(new EmbedderHealth(), new OnnxModelLoader(), "models/bge-small-zh-v1.5", 512);
        }

        @Override
        public Optional<float[]> embed(String text) {
            lastText.set(text);
            return Optional.of(new float[]{0.1f, 0.2f, 0.3f});
        }
    }

    // ------------------------------------------------------------------
    // 注册 + job_id + worker 文档文本
    // ------------------------------------------------------------------

    @Test
    void registersTaskInRegistry() {
        TaskRegistry registry = new TaskRegistry();
        EmbeddingSyncTask task = new EmbeddingSyncTask(null, registry, null, null);
        task.init();
        assertTrue(registry.contains(EmbeddingSyncTask.TASK_NAME), "taskName=embedding_sync 应已注册");
        assertNotNull(registry.get(EmbeddingSyncTask.TASK_NAME).orElse(null));
    }

    @Test
    void jobIdFormat() {
        assertEquals("embedding_sync:42", EmbeddingSyncTask.jobId(42));
    }

    @Test
    void workerDocTextMatchesPythonComposition() throws Exception {
        // 对齐 Python: f"{city} {name} {description} {tags_str} {category}"
        FakeEmbedder embedder = new FakeEmbedder();
        EmbeddingSyncTask task = new EmbeddingSyncTask(null, null, embedder, null);

        Map<String, Object> args = Map.of(
            "spot_id", 1,
            "city", "北京",
            "name", "故宫",
            "description", "历史建筑",
            "tags", List.of("文化", "古建筑"),
            "category", "attraction");
        // worker 在 embedding 可用时走到 SQL；这里没有 JdbcTemplate，会 NPE——
        // 先断言 embedder 收到的文本正确
        try {
            task.syncSpotEmbedding(args);
        } catch (Exception e) {
            // 期望走到 SQL（jdbcTemplate null → NPE 或 vector 错误）；文本断言先行
        }
        assertEquals("北京 故宫 历史建筑 文化 古建筑 attraction", embedder.lastText.get());
    }

    @Test
    void workerThrowsWhenEmbeddingUnavailable() {
        // 真实 BgeEmbedder 未预热 → embed 返回 empty → 抛异常（触发 max_tries=3 重试）
        EmbedderHealth health = new EmbedderHealth();
        BgeEmbedder embedder = new BgeEmbedder(health, new OnnxModelLoader(), "models/bge-small-zh-v1.5", 512);
        EmbeddingSyncTask task = new EmbeddingSyncTask(null, null, embedder, null);

        Map<String, Object> args = Map.of("spot_id", 1, "city", "北京", "name", "故宫",
            "description", "历史", "tags", List.of(), "category", "attraction");
        Exception e = assertThrows(Exception.class, () -> task.syncSpotEmbedding(args));
        assertTrue(e.getMessage().contains("embedding unavailable"), "应抛出 embedding 不可用异常: " + e.getMessage());
    }

    // ------------------------------------------------------------------
    // 判定 2：同 spot_id 重复入队只执行一次
    // ------------------------------------------------------------------

    @Test
    void duplicateEnqueueExecutesOnce() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        AtomicInteger count = new AtomicInteger();
        CountDownLatch executed = new CountDownLatch(1);
        registry.register(EmbeddingSyncTask.TASK_NAME, args -> {
            count.incrementAndGet();
            executed.countDown();
            return Map.of("spot_id", args.get("spot_id"), "status", "ok");
        });

        TaskQueue queue = newTaskQueue(registry);
        // 注意：不调用 init()——enqueue 路径不依赖 worker 注册，避免真实 worker 覆盖计数 handler
        EmbeddingSyncTask task = new EmbeddingSyncTask(queue, registry, null, null);

        // 同 spot_id 重复入队 → 只执行一次
        String job1 = task.enqueue(7, "北京", "故宫", "历史", List.of(), "attraction");
        String job2 = task.enqueue(7, "北京", "故宫", "历史", List.of(), "attraction");

        assertEquals(job1, job2, "job_id 相同");
        assertEquals("embedding_sync:7", job1);
        assertTrue(executed.await(5, TimeUnit.SECONDS), "任务应执行");
        // 等待潜在的第二次执行窗口
        Thread.sleep(300);
        assertEquals(1, count.get(), "同 spot_id 重复入队只执行一次");
    }

    @Test
    void differentSpotIdsExecuteSeparately() throws Exception {
        TaskRegistry registry = new TaskRegistry();
        AtomicInteger count = new AtomicInteger();
        CountDownLatch executed = new CountDownLatch(2);
        registry.register(EmbeddingSyncTask.TASK_NAME, args -> {
            count.incrementAndGet();
            executed.countDown();
            return Map.of("spot_id", args.get("spot_id"), "status", "ok");
        });

        TaskQueue queue = newTaskQueue(registry);
        EmbeddingSyncTask task = new EmbeddingSyncTask(queue, registry, null, null);

        task.enqueue(1, "北京", "故宫", "历史", List.of(), "attraction");
        task.enqueue(2, "北京", "长城", "风光", List.of(), "attraction");

        assertTrue(executed.await(5, TimeUnit.SECONDS));
        assertEquals(2, count.get(), "不同 spot_id 各执行一次");
    }
}
