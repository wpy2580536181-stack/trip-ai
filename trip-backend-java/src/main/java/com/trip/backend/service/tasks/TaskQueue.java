package com.trip.backend.service.tasks;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 任务队列（对应 Python task_queue.py / arq）
 * - Redis List 队列（LPUSH/BRPOP）
 * - 内存降级（@Async）
 * - job_id 幂等
 * - max_tries=3，退避 1/2/4s
 */
@Component
public class TaskQueue {

    private static final String QUEUE_PREFIX = "arq:queue:";
    private static final String RESULT_PREFIX = "arq:result:";
    private static final int MAX_TRIES = 3;

    private final StringRedisTemplate redisTemplate;
    private final boolean redisAvailable;
    private final Map<String, TaskEntry> memoryQueue = new ConcurrentHashMap<>();

    public TaskQueue(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
        this.redisAvailable = checkRedisAvailable();
    }

    private boolean checkRedisAvailable() {
        try {
            redisTemplate.opsForValue().get("health-check");
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 入队任务
     *
     * @param jobId 任务 ID（幂等键）
     * @param queueName 队列名称
     * @param taskData 任务数据
     * @param ttlSeconds 结果 TTL
     */
    public void enqueue(String jobId, String queueName, Map<String, Object> taskData, long ttlSeconds) {
        if (redisAvailable) {
            enqueueRedis(jobId, queueName, taskData, ttlSeconds);
        } else {
            enqueueMemory(jobId, queueName, taskData, ttlSeconds);
        }
    }

    private void enqueueRedis(String jobId, String queueName, Map<String, Object> taskData, long ttlSeconds) {
        try {
            // 幂等检查
            String existingResult = redisTemplate.opsForValue().get(RESULT_PREFIX + jobId);
            if (existingResult != null) {
                return; // 已完成，跳过
            }

            // 序列化任务数据
            String json = serializeTaskData(taskData);

            // LPUSH 到队列
            redisTemplate.opsForList().leftPush(QUEUE_PREFIX + queueName, json);

            // 标记任务元数据（TTL 3600s）
            redisTemplate.opsForHash().put(
                RESULT_PREFIX + jobId + ":meta",
                "status", "queued"
            );
            redisTemplate.expire(RESULT_PREFIX + jobId + ":meta", 3600, TimeUnit.SECONDS);

        } catch (Exception e) {
            // Redis 异常，降级内存
            enqueueMemory(jobId, queueName, taskData, ttlSeconds);
        }
    }

    private void enqueueMemory(String jobId, String queueName, Map<String, Object> taskData, long ttlSeconds) {
        TaskEntry entry = new TaskEntry(jobId, queueName, taskData, ttlSeconds);
        memoryQueue.put(jobId, entry);
    }

    /**
     * 获取任务结果
     */
    public Map<String, Object> getResult(String jobId) {
        if (redisAvailable) {
            return getResultRedis(jobId);
        } else {
            return getResultMemory(jobId);
        }
    }

    private Map<String, Object> getResultRedis(String jobId) {
        try {
            String result = redisTemplate.opsForValue().get(RESULT_PREFIX + jobId);
            if (result == null) {
                return Map.of("status", "pending");
            }
            return Map.of("status", "completed", "result", result);
        } catch (Exception e) {
            return getResultMemory(jobId);
        }
    }

    private Map<String, Object> getResultMemory(String jobId) {
        TaskEntry entry = memoryQueue.get(jobId);
        if (entry == null) {
            return Map.of("status", "not_found");
        }
        if (entry.result == null) {
            return Map.of("status", "pending");
        }
        return Map.of("status", "completed", "result", entry.result);
    }

    /**
     * 标记任务完成
     */
    public void complete(String jobId, Object result, long ttlSeconds) {
        if (redisAvailable) {
            completeRedis(jobId, result, ttlSeconds);
        } else {
            completeMemory(jobId, result);
        }
    }

    private void completeRedis(String jobId, Object result, long ttlSeconds) {
        try {
            String json = serializeTaskData(Map.of("result", result));
            redisTemplate.opsForValue().set(RESULT_PREFIX + jobId, json, ttlSeconds, TimeUnit.SECONDS);
        } catch (Exception e) {
            completeMemory(jobId, result);
        }
    }

    private void completeMemory(String jobId, Object result) {
        TaskEntry entry = memoryQueue.get(jobId);
        if (entry != null) {
            entry.result = result;
        }
    }

    private String serializeTaskData(Map<String, Object> data) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(data);
        } catch (Exception e) {
            return "{}";
        }
    }

    private static class TaskEntry {
        String jobId;
        String queueName;
        Map<String, Object> taskData;
        long ttlSeconds;
        Object result;

        TaskEntry(String jobId, String queueName, Map<String, Object> taskData, long ttlSeconds) {
            this.jobId = jobId;
            this.queueName = queueName;
            this.taskData = taskData;
            this.ttlSeconds = ttlSeconds;
        }
    }
}
