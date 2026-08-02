package com.trip.backend.service.llm;

/**
 * Provider 健康状态
 */
public enum HealthState {
    HEALTHY,    // 健康
    DEGRADED,   // 降级（连续失败 3 次）
    DOWN        // 不可用（连续失败 5 次）
}
