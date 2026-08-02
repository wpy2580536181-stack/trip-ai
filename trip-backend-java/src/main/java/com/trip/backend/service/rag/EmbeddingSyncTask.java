package com.trip.backend.service.rag;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.service.tasks.TaskQueue;
import com.trip.backend.service.tasks.TaskRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Embedding 同步任务
 *
 * 对应 Python services/tasks/embedding_sync.py
 *
 * 功能：
 * - 异步计算 Spot embedding 并写入 PG
 * - 失败重试（max_tries=3）
 * - 幂等键 job_id = embedding_sync:{job_kind}:{spot_id}
 */
@Service
public class EmbeddingSyncTask {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingSyncTask.class);

    private final TaskQueue taskQueue;
    private final TaskRegistry taskRegistry;
    private final BgeEmbedder embedder;

    public EmbeddingSyncTask(TaskQueue taskQueue, TaskRegistry taskRegistry, BgeEmbedder embedder) {
        this.taskQueue = taskQueue;
        this.taskRegistry = taskRegistry;
        this.embedder = embedder;
    }

    /**
     * 入队单个 Spot embedding 计算
     *
     * @param spotId Spot ID
     * @param city 城市
     * @param name 名称
     * @param description 描述
     * @param tags 标签
     * @param category 分类
     * @param jobKind 任务类型（create/update）
     * @return Job ID
     */
    public String enqueueSpotEmbedding(Long spotId, String city, String name, String description,
                                       Object tags, String category, String jobKind) {
        String jobId = String.format("embedding_sync:%s:%d", jobKind, spotId);

        // 构建文档文本
        String tagsStr = tags instanceof String ? (String) tags : "";
        String docText = String.format("%s %s %s %s %s", city, name, description, tagsStr, category);

        // 注册任务（幂等键）
        taskRegistry.register("embedding_sync", jobId, ctx -> {
            try {
                float[] embedding = embedder.embed(docText);

                // 写入 PG（使用 JdbcTemplate 或 EntityManager）
                // TODO: C4 实现后补充实际更新逻辑

                log.info("[EmbeddingSyncTask] Spot embedding updated: spot_id={}, name={}", spotId, name);
                return Map.of("spot_id", spotId, "status", "ok");
            } catch (Exception e) {
                log.error("[EmbeddingSyncTask] Failed to sync embedding: spot_id={}", spotId, e);
                throw e; // 抛出异常触发重试
            }
        });

        // 入队
        taskQueue.enqueue("embedding_sync", jobId, spotId);

        return jobId;
    }

    /**
     * 批量入队
     *
     * @param spots Spot 列表
     * @return Job IDs
     */
    public java.util.List<String> enqueueBulkEmbedding(java.util.List<Spot> spots) {
        return spots.stream()
            .map(spot -> enqueueSpotEmbedding(
                spot.getId(),
                spot.getCity(),
                spot.getName(),
                spot.getDescription() != null ? spot.getDescription() : "",
                spot.getTags(),
                spot.getCategory(),
                "bulk"
            ))
            .toList();
    }
}
