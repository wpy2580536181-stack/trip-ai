package com.trip.backend.task;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.task.TaskQueue;
import com.trip.backend.infra.task.TaskRegistry;
import com.trip.backend.service.rag.VectorSearchSpots;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Spot embedding 异步同步任务（对应 Python src/services/tasks/embedding_sync.py）。
 *
 * - 入队：taskName="embedding_sync"，job_id = "embedding_sync:{spotId}"（幂等，重复以最新为准）
 * - worker：对齐 Python sync_spot_embedding——由入队参数构造文档文本
 *   `city name description tags_str category`，BgeEmbedder 算向量后
 *   `UPDATE spots SET embedding=CAST(:vec AS vector) WHERE id=:id`
 * - embedding 不可用 → 抛异常 → 队列退避重试（max_tries=3）
 */
@Component
public class EmbeddingSyncTask {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingSyncTask.class);

    public static final String TASK_NAME = "embedding_sync";

    private final TaskQueue taskQueue;
    private final TaskRegistry registry;
    private final BgeEmbedder embedder;
    private final JdbcTemplate jdbcTemplate;

    public EmbeddingSyncTask(TaskQueue taskQueue,
                             TaskRegistry registry,
                             BgeEmbedder embedder,
                             JdbcTemplate jdbcTemplate) {
        this.taskQueue = taskQueue;
        this.registry = registry;
        this.embedder = embedder;
        this.jdbcTemplate = jdbcTemplate;
    }

    /** 注册 worker 到 TaskRegistry（对齐 Python arq worker 注册）。 */
    @PostConstruct
    public void init() {
        registry.register(TASK_NAME, this::syncSpotEmbedding);
        log.info("embedding_sync_task_registered");
    }

    /** 幂等 job_id。 */
    public static String jobId(long spotId) {
        return TASK_NAME + ":" + spotId;
    }

    /**
     * 入队单个 spot embedding 计算任务（幂等：相同 spot_id 重复入队只执行一次）。
     *
     * @return jobId
     */
    public String enqueue(long spotId, String city, String name, String description,
                          List<String> tags, String category) {
        Map<String, Object> args = new LinkedHashMap<>();
        args.put("spot_id", spotId);
        args.put("city", city == null ? "" : city);
        args.put("name", name == null ? "" : name);
        args.put("description", description == null ? "" : description);
        args.put("tags", tags == null ? List.of() : tags);
        args.put("category", category == null ? "" : category);
        return taskQueue.enqueue(TASK_NAME, args, jobId(spotId));
    }

    /**
     * worker：计算 Spot embedding 并写入 PG spots.embedding 列（对齐 Python sync_spot_embedding）。
     * embedding 不可用 / spot 不存在 → 抛异常触发退避重试（max_tries=3）。
     */
    public Map<String, Object> syncSpotEmbedding(Map<String, Object> args) throws Exception {
        long spotId = ((Number) args.get("spot_id")).longValue();
        String city = str(args.get("city"));
        String name = str(args.get("name"));
        String description = str(args.get("description"));
        String category = str(args.get("category"));
        Object tagsObj = args.get("tags");
        List<?> tags = tagsObj instanceof List<?> list ? list : List.of();
        String tagsStr = String.join(" ", tags.stream().map(String::valueOf).toList());

        // 与 Python 一致：f"{city} {name} {description} {tags_str} {category}"
        String docText = city + " " + name + " " + description + " " + tagsStr + " " + category;

        Optional<float[]> vec = embedder.embed(docText);
        if (vec.isEmpty()) {
            throw new IllegalStateException("embedding unavailable, will retry");
        }

        int updated = jdbcTemplate.update(
            "UPDATE spots SET embedding = CAST(? AS vector) WHERE id = ?",
            VectorSearchSpots.toPgVectorString(vec.get()), spotId);
        if (updated == 0) {
            throw new IllegalStateException("spot not found: " + spotId);
        }
        log.info("spot_embedding_updated spot_id={}", spotId);
        return Map.of("spot_id", spotId, "status", "ok");
    }

    private String str(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
