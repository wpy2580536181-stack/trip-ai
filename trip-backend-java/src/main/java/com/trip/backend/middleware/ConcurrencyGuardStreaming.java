package com.trip.backend.middleware;

import com.trip.backend.domain.entity.User;
import com.trip.backend.middleware.TokenUsage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 并发守卫流式支持
 *
 * 对应 Python middleware/concurrency_guard.py
 *
 * 功能：
 * - 流式请求信号量管理
 * - 客户端断开时自动释放
 */
@Service
public class ConcurrencyGuardStreaming {

    private static final Logger log = LoggerFactory.getLogger(ConcurrencyGuardStreaming.class);

    // 用户级信号量（user_id → 计数）
    private final ConcurrentHashMap<Long, AtomicInteger> userConcurrency = new ConcurrentHashMap<>();

    // 全局信号量
    private final AtomicInteger globalConcurrency = new AtomicInteger(0);

    // 最大并发数
    private static final int MAX_USER_CONCURRENT = 3;
    private static final int MAX_GLOBAL_CONCURRENT = 50;

    /**
     * 尝试获取流式信号量
     *
     * @param userId 用户 ID
     * @return true 如果获取成功
     */
    public boolean tryAcquireStream(Long userId) {
        // 检查用户级并发
        int userCount = userConcurrency.computeIfAbsent(userId, k -> new AtomicInteger(0))
            .incrementAndGet();

        if (userCount > MAX_USER_CONCURRENT) {
            userConcurrency.get(userId).decrementAndGet();
            log.warn("[ConcurrencyGuard] User {} exceeds max concurrent streams ({})",
                userId, MAX_USER_CONCURRENT);
            return false;
        }

        // 检查全局并发
        int globalCount = globalConcurrency.incrementAndGet();
        if (globalCount > MAX_GLOBAL_CONCURRENT) {
            userConcurrency.get(userId).decrementAndGet();
            globalConcurrency.decrementAndGet();
            log.warn("[ConcurrencyGuard] Global concurrency limit exceeded ({})", MAX_GLOBAL_CONCURRENT);
            return false;
        }

        log.debug("[ConcurrencyGuard] Acquired stream: userId={}, userCount={}, globalCount={}",
            userId, userCount, globalCount);

        return true;
    }

    /**
     * 释放流式信号量
     *
     * @param userId 用户 ID
     */
    public void releaseStream(Long userId) {
        // 释放用户级
        AtomicInteger count = userConcurrency.get(userId);
        if (count != null) {
            int newCount = count.decrementAndGet();
            if (newCount <= 0) {
                userConcurrency.remove(userId, count);
            }
        }

        // 释放全局
        globalConcurrency.decrementAndGet();

        log.debug("[ConcurrencyGuard] Released stream: userId={}", userId);
    }
}
