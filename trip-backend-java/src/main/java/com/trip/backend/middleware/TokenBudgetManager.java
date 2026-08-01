package com.trip.backend.middleware;

import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Token 预算管理器（对应 Python middleware/token_budget.py）
 * - 用户 50K/h（超限 429）
 * - 全局 200K/min（超限 503）
 * - 固定窗口滑动重置
 */
public class TokenBudgetManager {

    // 用户预算
    private final long userLimit;
    private final long userWindowSeconds;

    // 全局预算
    private final long globalLimit;
    private final long globalWindowSeconds;

    // 用户状态（key=userId，value=(current, resetAtEpochSec)）
    private final ConcurrentHashMap<Long, TokenBucket> userBuckets = new ConcurrentHashMap<>();

    // 全局状态
    private volatile TokenBucket globalBucket;

    public TokenBudgetManager(long userLimit, long userWindowHours,
                             long globalLimit, long globalWindowMinutes) {
        this.userLimit = userLimit;
        this.userWindowSeconds = userWindowHours * 3600;
        this.globalLimit = globalLimit;
        this.globalWindowSeconds = globalWindowMinutes * 60;
    }

    /**
     * 检查用户预算
     */
    public BudgetResult checkUser(Long userId, int tokens) {
        long now = Instant.now().getEpochSecond();
        TokenBucket bucket = userBuckets.compute(userId, (k, existing) -> {
            if (existing == null || now >= existing.resetAt) {
                return new TokenBucket(tokens, now + userWindowSeconds);
            } else {
                existing.current += tokens;
                return existing;
            }
        });

        boolean allowed = bucket.current <= userLimit;
        return new BudgetResult(allowed, bucket.current, bucket.resetAt);
    }

    /**
     * 检查全局预算
     */
    public BudgetResult checkGlobal(int tokens) {
        long now = Instant.now().getEpochSecond();

        // 惰性重置
        TokenBucket current = globalBucket;
        if (current == null || now >= current.resetAt) {
            globalBucket = new TokenBucket(tokens, now + globalWindowSeconds);
            return new BudgetResult(true, tokens, globalBucket.resetAt);
        }

        current.current += tokens;
        boolean allowed = current.current <= globalLimit;
        return new BudgetResult(allowed, current.current, current.resetAt);
    }

    public record BudgetResult(boolean allowed, long current, long resetAt) {}

    private static class TokenBucket {
        long current;
        long resetAt;

        TokenBucket(long current, long resetAt) {
            this.current = current;
            this.resetAt = resetAt;
        }
    }
}
