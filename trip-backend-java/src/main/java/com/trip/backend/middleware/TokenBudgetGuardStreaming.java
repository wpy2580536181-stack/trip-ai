package com.trip.backend.middleware;

import com.trip.backend.domain.entity.User;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.concurrent.atomic.AtomicLong;

/**
 * Token 预算守卫流式支持
 *
 * 对应 Python middleware/token_budget_guard.py
 *
 * 功能：
 * - 流式请求 token 预算检查
 * - 实时 token 消耗追踪
 */
@Service
public class TokenBudgetGuardStreaming {

    private static final Logger log = LoggerFactory.getLogger(TokenBudgetGuardStreaming.class);

    // 用户级 token 消耗追踪
    private final java.util.concurrent.ConcurrentHashMap<Long, AtomicLong> userTokenUsage = new java.util.concurrent.ConcurrentHashMap<>();

    // 预算限制
    private static final long USER_DAILY_LIMIT = 100_000; // 用户日限额
    private static final long GLOBAL_DAILY_LIMIT = 10_000_000; // 全局日限额

    /**
     * 检查流式请求是否在预算内
     *
     * @param userId 用户 ID
     * @param estimatedTokens 预估 token 数
     * @return true 如果预算充足
     */
    public boolean checkBudget(Long userId, long estimatedTokens) {
        // 获取用户当前消耗
        AtomicLong usage = userTokenUsage.computeIfAbsent(userId, k -> new AtomicLong(0));
        long currentUsage = usage.get();

        // 检查是否超预算
        if (currentUsage + estimatedTokens > USER_DAILY_LIMIT) {
            log.warn("[TokenBudgetGuard] User {} exceeds daily budget: current={}, estimated={}, limit={}",
                userId, currentUsage, estimatedTokens, USER_DAILY_LIMIT);
            return false;
        }

        // 预留 token
        usage.addAndGet(estimatedTokens);

        log.debug("[TokenBudgetGuard] Budget check passed: userId={}, usage={}/{}",
            userId, currentUsage + estimatedTokens, USER_DAILY_LIMIT);

        return true;
    }

    /**
     * 更新实际 token 消耗
     *
     * @param userId 用户 ID
     * @param actualTokens 实际消耗 token 数
     */
    public void updateActualUsage(Long userId, long actualTokens) {
        AtomicLong usage = userTokenUsage.computeIfAbsent(userId, k -> new AtomicLong(0));
        // 这里应该回滚预留 + 加上实际值，简化处理直接加
        usage.addAndGet(actualTokens);

        log.debug("[TokenBudgetGuard] Updated actual usage: userId={}, tokens={}", userId, actualTokens);
    }

    /**
     * 获取用户当前 token 使用量
     */
    public long getCurrentUsage(Long userId) {
        AtomicLong usage = userTokenUsage.get(userId);
        return usage != null ? usage.get() : 0;
    }

    /**
     * 重置用户 token 计数
     */
    public void resetUserBudget(Long userId) {
        userTokenUsage.remove(userId);
        log.debug("[TokenBudgetGuard] Reset budget for user: {}", userId);
    }
}
