package com.trip.backend.middleware;

import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

/**
 * 并发守卫（对应 Python middleware/concurrency_guard.py）
 * - 全局 Semaphore(10)
 * - 每用户 Semaphore(1)
 * - 非阻塞获取，超限抛出 ConcurrencyLimitException
 */
public class ConcurrencyGuard {

    private final Semaphore globalSemaphore;
    private final Semaphore perUserSemaphore;
    private final java.util.Map<Long, Semaphore> userSemaphores = new java.util.concurrent.ConcurrentHashMap<>();

    public ConcurrencyGuard(int globalLimit, int perUserLimit) {
        this.globalSemaphore = new Semaphore(globalLimit, true);
        this.perUserSemaphore = new Semaphore(perUserLimit, true);
    }

    /**
     * 尝试获取并发许可
     *
     * @param userId 用户 ID（null 表示匿名）
     * @throws ConcurrencyLimitException 超限时抛出
     */
    public void acquire(Long userId) throws ConcurrencyLimitException {
        // 1. 尝试获取全局许可
        if (!globalSemaphore.tryAcquire()) {
            throw new ConcurrencyLimitException("Global concurrency limit reached");
        }

        // 2. 尝试获取用户许可
        Semaphore userSem = userSemaphores.computeIfAbsent(
            userId != null ? userId : -1L,
            k -> new Semaphore(1, true)
        );

        if (!userSem.tryAcquire()) {
            // 回滚全局许可
            globalSemaphore.release();
            throw new ConcurrencyLimitException("User concurrency limit reached");
        }
    }

    /**
     * 释放并发许可
     */
    public void release(Long userId) {
        Semaphore userSem = userSemaphores.get(userId != null ? userId : -1L);
        if (userSem != null) {
            userSem.release();
        }
        globalSemaphore.release();
    }

    /**
     * 带超时的获取
     */
    public boolean tryAcquire(Long userId, long timeout, TimeUnit unit) throws InterruptedException {
        boolean globalAcquired = globalSemaphore.tryAcquire(timeout, unit);
        if (!globalAcquired) {
            return false;
        }

        Semaphore userSem = userSemaphores.computeIfAbsent(
            userId != null ? userId : -1L,
            k -> new Semaphore(1, true)
        );

        boolean userAcquired = userSem.tryAcquire(timeout, unit);
        if (!userAcquired) {
            globalSemaphore.release();
            return false;
        }

        return true;
    }

    public static class ConcurrencyLimitException extends Exception {
        public ConcurrencyLimitException(String message) {
            super(message);
        }
    }
}
