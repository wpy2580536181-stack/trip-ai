package com.trip.backend.infra.resilience;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 熔断器（三态机：CLOSED / OPEN / HALF_OPEN）
 *
 * 对应 Python resilience.py::CircuitBreaker
 *
 * 状态转换：
 * - CLOSED → OPEN：连续失败达到 threshold（默认 5）
 * - OPEN → HALF_OPEN：经过 recovery_timeout（默认 30s）
 * - HALF_OPEN → CLOSED：试探成功
 * - HALF_OPEN → OPEN：试探失败
 *
 * 设计要点：
 * - 按 tool name 共享（同一 tool 多次调用共享同一熔断器）
 * - CLOSED 状态下成功不重置 failure_count（用连续失败判定熔断）
 */
public class CircuitBreaker {

    private static final Logger log = LoggerFactory.getLogger(CircuitBreaker.class);

    /** 熔断器状态 */
    public enum State {
        CLOSED,   // 正常：所有请求通过
        OPEN,     // 熔断：直接走 fallback
        HALF_OPEN // 试探：放行 1 个请求试探恢复
    }

    private final String name;
    private final int failureThreshold;
    private final long recoveryTimeoutMs;

    // 状态（volatile 保证可见性）
    private volatile State state = State.CLOSED;
    private final AtomicInteger failureCount = new AtomicInteger(0);
    private volatile long lastFailureAt = 0;

    // 按 name 共享的熔断器注册表
    private static final ConcurrentHashMap<String, CircuitBreaker> registry = new ConcurrentHashMap<>();

    private CircuitBreaker(String name, int failureThreshold, long recoveryTimeoutMs) {
        this.name = name;
        this.failureThreshold = failureThreshold;
        this.recoveryTimeoutMs = recoveryTimeoutMs;
    }

    /**
     * 获取或创建熔断器（按 name 共享）
     */
    public static CircuitBreaker getOrCreate(String name, int failureThreshold, long recoveryTimeoutMs) {
        return registry.computeIfAbsent(
            name + ":" + failureThreshold + ":" + recoveryTimeoutMs,
            key -> new CircuitBreaker(name, failureThreshold, recoveryTimeoutMs)
        );
    }

    /**
     * 检查是否允许请求通过
     *
     * @return true 表示允许调用下游
     */
    public boolean allowRequest() {
        if (state == State.CLOSED) {
            return true;
        }

        if (state == State.OPEN) {
            // 检查是否到 recovery_timeout
            long now = System.currentTimeMillis();
            if (now - lastFailureAt >= recoveryTimeoutMs) {
                transition(State.HALF_OPEN, "recovery_timeout_reached");
                return true;
            }
            return false;
        }

        // HALF_OPEN：放行 1 个试探请求
        return true;
    }

    /**
     * 记录成功调用
     */
    public void recordSuccess() {
        if (state == State.HALF_OPEN) {
            transition(State.CLOSED, "probe_success");
            // 成功恢复，重置失败计数
            failureCount.set(0);
        }
        // CLOSED 状态下成功不重置 failure_count（避免偶发成功打断连续失败累积）
    }

    /**
     * 记录失败调用
     */
    public void recordFailure() {
        int count = failureCount.incrementAndGet();
        lastFailureAt = System.currentTimeMillis();

        if (state == State.HALF_OPEN) {
            // 试探失败 → 重新熔断
            transition(State.OPEN, "probe_failed");
            return;
        }

        if (state == State.CLOSED && count >= failureThreshold) {
            transition(State.OPEN, "failure_threshold_reached");
        }
    }

    /**
     * 状态转换（内部用）
     */
    private void transition(State newState, String reason) {
        State oldState = this.state;
        if (oldState == newState) {
            return;
        }

        this.state = newState;

        if (newState == State.CLOSED) {
            failureCount.set(0);
        }

        log.info("[CircuitBreaker] {} state transition: {} → {} (reason: {}, failures: {})",
            name, oldState, newState, reason, failureCount.get());
    }

    /**
     * 手动重置（测试/管理用）
     */
    public void reset() {
        transition(State.CLOSED, "manual_reset");
        failureCount.set(0);
        lastFailureAt = 0;
    }

    // ==================== Getters ====================

    public State getState() {
        return state;
    }

    public int getFailureCount() {
        return failureCount.get();
    }

    public String getName() {
        return name;
    }
}
