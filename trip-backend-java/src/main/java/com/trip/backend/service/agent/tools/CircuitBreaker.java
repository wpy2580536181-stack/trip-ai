package com.trip.backend.service.agent.tools;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 工具熔断器（对应 Python resilience.py CircuitBreaker）。
 *
 * 三态机：
 * - CLOSED：正常通过；连续失败达 threshold → OPEN
 * - OPEN：拒绝所有请求走 fallback；经过 recoveryTimeout → HALF_OPEN
 * - HALF_OPEN：放行 1 个试探请求；成功 → CLOSED，失败 → OPEN
 *
 * 按 tool name 进程内共享（getOrCreate）。
 */
public class CircuitBreaker {

    public enum State { CLOSED, OPEN, HALF_OPEN }

    private final String name;
    private final int failureThreshold;
    private final long recoveryTimeoutMs;

    private volatile State state = State.CLOSED;
    private int failureCount;
    private long lastFailureAt;

    private static final Map<String, CircuitBreaker> REGISTRY = new ConcurrentHashMap<>();

    private CircuitBreaker(String name, int failureThreshold, long recoveryTimeoutMs) {
        this.name = name;
        this.failureThreshold = failureThreshold;
        this.recoveryTimeoutMs = recoveryTimeoutMs;
    }

    /** 按 name+threshold+timeout 共享同一熔断器。 */
    public static CircuitBreaker getOrCreate(String name, int failureThreshold, long recoveryTimeoutMs) {
        return REGISTRY.computeIfAbsent(
            name + ":" + failureThreshold + ":" + recoveryTimeoutMs,
            k -> new CircuitBreaker(name, failureThreshold, recoveryTimeoutMs));
    }

    public String name() {
        return name;
    }

    public State state() {
        return state;
    }

    public int failureCount() {
        return failureCount;
    }

    /** 是否允许请求通过（OPEN 且未到恢复时间则拒绝）。 */
    public synchronized boolean allowRequest() {
        if (state == State.CLOSED) {
            return true;
        }
        if (state == State.OPEN) {
            if (lastFailureAt > 0 && System.currentTimeMillis() - lastFailureAt >= recoveryTimeoutMs) {
                transition(State.HALF_OPEN);
                return true;
            }
            return false;
        }
        // HALF_OPEN：放行试探
        return true;
    }

    public synchronized void recordSuccess() {
        if (state == State.HALF_OPEN) {
            transition(State.CLOSED);
        }
        // CLOSED 下成功不重置 failureCount（按连续失败判定）
    }

    public synchronized void recordFailure() {
        failureCount++;
        lastFailureAt = System.currentTimeMillis();
        if (state == State.HALF_OPEN) {
            transition(State.OPEN);
            return;
        }
        if (state == State.CLOSED && failureCount >= failureThreshold) {
            transition(State.OPEN);
        }
    }

    public synchronized void reset() {
        transition(State.CLOSED);
        failureCount = 0;
        lastFailureAt = 0;
    }

    private void transition(State newState) {
        if (state == newState) {
            return;
        }
        state = newState;
        if (newState == State.CLOSED) {
            failureCount = 0;
        }
    }
}
