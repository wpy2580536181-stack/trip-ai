package com.trip.backend.infra.task;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 任务队列门面（对应 Python src/services/task_queue.py TaskQueue）。
 *
 * 双后端：
 * - Redis 可用 → LPUSH arq:queue:{name} 入队 + SETNX 幂等（WorkerScheduler 消费，
 *   结果 SETEX arq:result:{jobId} 3600）
 * - Redis 不可用 → DegradedTaskRunner 虚拟线程内存执行（绝不抛错给上游）
 *
 * - job_id 幂等：相同 job_id 重复入队只执行一次（进程内 map + Redis SETNX 双保险）
 * - 调用方完全无感：enqueue() 后由后端各自执行
 */
@Component
public class TaskQueue {

    private static final Logger log = LoggerFactory.getLogger(TaskQueue.class);

    public static final long RESULT_TTL_SECONDS = 3600;

    private final StringRedisTemplate redisTemplate;
    private final TaskRegistry registry;
    private final DegradedTaskRunner degradedTaskRunner;
    private final WorkerScheduler workerScheduler;
    private final ObjectMapper objectMapper = new ObjectMapper();
    /** 进程内幂等键：jobId → 已入队（对齐 arq _job_id：同 job_id 只执行一次）。 */
    private final Map<String, Boolean> enqueuedJobs = new ConcurrentHashMap<>();

    public TaskQueue(StringRedisTemplate redisTemplate,
                     TaskRegistry registry,
                     DegradedTaskRunner degradedTaskRunner,
                     WorkerScheduler workerScheduler) {
        this.redisTemplate = redisTemplate;
        this.registry = registry;
        this.degradedTaskRunner = degradedTaskRunner;
        this.workerScheduler = workerScheduler;
    }

    /**
     * 入队任务（幂等）。
     *
     * @param taskName 注册在 {@link TaskRegistry} 的任务名
     * @param args     任务参数（JSON 可序列化）
     * @param jobId    幂等键；相同 job_id 重复入队只执行一次
     * @return jobId（入队成功）；重复入队时同样返回 jobId 但不再执行
     */
    public String enqueue(String taskName, Map<String, Object> args, String jobId) {
        if (registry.get(taskName).isEmpty()) {
            throw new IllegalArgumentException("task not registered: " + taskName);
        }
        // 幂等：相同 job_id 只执行一次
        if (jobId != null && enqueuedJobs.putIfAbsent(jobId, Boolean.TRUE) != null) {
            return jobId;
        }

        // 路径 1：Redis 后端（可靠投递 + 幂等 SETNX）
        try {
            if (jobId != null) {
                Boolean first = redisTemplate.opsForValue()
                    .setIfAbsent("arq:job:" + jobId, "1", RESULT_TTL_SECONDS, TimeUnit.SECONDS);
                if (Boolean.FALSE.equals(first)) {
                    return jobId; // Redis 侧已存在，不重复入队
                }
            }
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("job_id", jobId);
            payload.put("task", taskName);
            payload.put("args", args);
            redisTemplate.opsForList().leftPush("arq:queue:" + taskName, objectMapper.writeValueAsString(payload));
            workerScheduler.ensureStarted(taskName);
            return jobId;
        } catch (Exception e) {
            // 路径 2：内存降级（Redis 不可用/序列化失败，绝不抛错给上游）
            log.warn("task_queue_redis_enqueue_failed_falling_back task={} job={} error={}",
                taskName, jobId, e.getMessage());
            degradedTaskRunner.submit(taskName, args, jobId);
            return jobId;
        }
    }

    /** 读取任务结果：Redis 结果优先，其次内存降级结果（TTL 均 3600s）。 */
    public Optional<Object> getResult(String jobId) {
        try {
            String value = redisTemplate.opsForValue().get("arq:result:" + jobId);
            if (value != null) {
                return Optional.of(objectMapper.readValue(value, new TypeReference<Map<String, Object>>() {
                }));
            }
        } catch (Exception e) {
            // Redis 不可用或未命中 → 查内存
        }
        return degradedTaskRunner.getResult(jobId);
    }
}
