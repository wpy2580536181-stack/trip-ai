package com.trip.backend.service.llm;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Provider 健康注册表（对应 Python provider_router/health.py）
 * - 连续失败 3 次 → DEGRADED
 * - 连续失败 5 次 → DOWN
 * - 60s 自动恢复 → HEALTHY
 */
public class ProviderHealthRegistry {

    private final Map<ProviderId, HealthState> healthStates = new ConcurrentHashMap<>();
    private final Map<ProviderId, AtomicInteger> failureCounts = new ConcurrentHashMap<>();
    private final Map<ProviderId, Long> lastFailureTimes = new ConcurrentHashMap<>();

    private static final int DEGRADED_THRESHOLD = 3;
    private static final int DOWN_THRESHOLD = 5;
    private static final long RECOVERY_WINDOW_MS = 60 * 1000; // 60s

    /**
     * 记录失败
     */
    public void recordFailure(ProviderId provider) {
        AtomicInteger count = failureCounts.computeIfAbsent(provider, k -> new AtomicInteger(0));
        int failures = count.incrementAndGet();
        lastFailureTimes.put(provider, System.currentTimeMillis());

        if (failures >= DOWN_THRESHOLD) {
            healthStates.put(provider, HealthState.DOWN);
        } else if (failures >= DEGRADED_THRESHOLD) {
            healthStates.put(provider, HealthState.DEGRADED);
        }
    }

    /**
     * 记录成功
     */
    public void recordSuccess(ProviderId provider) {
        failureCounts.remove(provider);
        lastFailureTimes.remove(provider);
        healthStates.put(provider, HealthState.HEALTHY);
    }

    /**
     * 获取健康状态（含自动恢复检查）
     */
    public HealthState getHealthState(ProviderId provider) {
        // 检查是否自动恢复
        Long lastFailure = lastFailureTimes.get(provider);
        if (lastFailure != null) {
            long elapsed = System.currentTimeMillis() - lastFailure;
            if (elapsed >= RECOVERY_WINDOW_MS) {
                // 60s 无新失败，恢复为 HEALTHY
                failureCounts.remove(provider);
                lastFailureTimes.remove(provider);
                healthStates.put(provider, HealthState.HEALTHY);
                return HealthState.HEALTHY;
            }
        }

        return healthStates.getOrDefault(provider, HealthState.HEALTHY);
    }

    /**
     * 重置状态
     */
    public void reset(ProviderId provider) {
        failureCounts.remove(provider);
        lastFailureTimes.remove(provider);
        healthStates.put(provider, HealthState.HEALTHY);
    }
}
