package com.trip.backend.infra.ratelimit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 限流器（对应 Python rate_limiter.py）
 * - 固定窗口算法
 * - Redis INCR + EXPIRE，降级内存
 * - 返回 (count, resetAt)
 */
@Component
public class RateLimiter {

    private final StringRedisTemplate redisTemplate;
    private final boolean redisAvailable;

    // 内存降级：key -> (count, resetAtEpochSec)
    private final ConcurrentHashMap<String, MemoryBucket> memoryBuckets = new ConcurrentHashMap<>();

    public RateLimiter(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
        this.redisAvailable = checkRedisAvailable();
    }

    /**
     * 检查 Redis 是否可用
     */
    private boolean checkRedisAvailable() {
        try {
            redisTemplate.opsForValue().get("health-check");
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 限流检查
     *
     * @param key 限流键（如 userId 或 IP）
     * @param config 限流配置
     * @return RateLimitResult (allowed, currentCount, resetAt)
     */
    public RateLimitResult check(String key, RateLimitConfig config) {
        if (redisAvailable) {
            return checkWithRedis(key, config);
        } else {
            return checkWithMemory(key, config);
        }
    }

    /**
     * Redis 实现
     */
    private RateLimitResult checkWithRedis(String key, RateLimitConfig config) {
        try {
            String redisKey = "rate_limit:" + config.getName() + ":" + key;
            Long count = redisTemplate.opsForValue().increment(redisKey);

            if (count == 1) {
                // 首次请求，设置过期时间
                redisTemplate.expire(redisKey, config.getWindowSeconds(), java.util.concurrent.TimeUnit.SECONDS);
            }

            long resetAt = Instant.now().getEpochSecond() + config.getWindowSeconds();

            boolean allowed = count <= config.getMaxRequests();
            return new RateLimitResult(allowed, count.intValue(), resetAt);
        } catch (Exception e) {
            // Redis 异常，降级内存
            return checkWithMemory(key, config);
        }
    }

    /**
     * 内存降级实现
     */
    private RateLimitResult checkWithMemory(String key, RateLimitConfig config) {
        String memKey = config.getName() + ":" + key;
        long now = Instant.now().getEpochSecond();

        MemoryBucket bucket = memoryBuckets.compute(memKey, (k, existing) -> {
            if (existing == null || now >= existing.resetAt) {
                // 新窗口
                return new MemoryBucket(1, now + config.getWindowSeconds());
            } else {
                // 当前窗口
                existing.count.incrementAndGet();
                return existing;
            }
        });

        boolean allowed = bucket.count.get() <= config.getMaxRequests();
        return new RateLimitResult(allowed, bucket.count.get(), bucket.resetAt);
    }

    /**
     * 限流结果
     */
    public record RateLimitResult(boolean allowed, int currentCount, long resetAt) {}

    /**
     * 内存 Bucket
     */
    private static class MemoryBucket {
        AtomicInteger count;
        long resetAt;

        MemoryBucket(int count, long resetAt) {
            this.count = new AtomicInteger(count);
            this.resetAt = resetAt;
        }
    }
}
