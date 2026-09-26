package com.trip.backend.service.llm;

import java.util.List;
import java.util.function.Function;

/**
 * Provider 路由（对应 Python provider_router/router.py）
 */
public class ProviderRouter {

    private final ProviderConfig config;
    private final ProviderHealthRegistry healthRegistry;

    // 场景优先级映射
    private static final java.util.Map<Scenario, List<ProviderId>> PRIORITY_MAP = java.util.Map.of(
        Scenario.PLANNING, List.of(ProviderId.DEEPSEEK),
        Scenario.CHAT, List.of(ProviderId.DEEPSEEK),
        Scenario.RESEARCH, List.of(ProviderId.DEEPSEEK)
    );

    public ProviderRouter(ProviderConfig config, ProviderHealthRegistry healthRegistry) {
        this.config = config;
        this.healthRegistry = healthRegistry;
    }

    /**
     * 选择最佳 Provider
     */
    public ProviderId select(Scenario scenario) {
        List<ProviderId> priority = PRIORITY_MAP.get(scenario);
        if (priority == null) {
            priority = List.of(ProviderId.DEEPSEEK, ProviderId.KIMI, ProviderId.AGNESE);
        }

        // 选择第一个 HEALTHY 的 provider
        for (ProviderId provider : priority) {
            if (healthRegistry.getHealthState(provider) == HealthState.HEALTHY) {
                return provider;
            }
        }

        // 全部 DOWN，返回第一个（让调用方处理失败）
        return priority.get(0);
    }

    /**
     * 带 fallback 的执行
     */
    public <T> T executeWithFallback(Scenario scenario, Function<ProviderId, T> primaryFn, Function<ProviderId, T> fallbackFn) {
        ProviderId primary = select(scenario);

        try {
            T result = primaryFn.apply(primary);
            healthRegistry.recordSuccess(primary);
            return result;
        } catch (Exception e) {
            healthRegistry.recordFailure(primary);

            // 尝试 fallback provider
            ProviderId fallback = selectFallback(scenario, primary);
            if (fallback != null && fallback != primary && fallbackFn != null) { // ✅ 添加 fallbackFn != null 检查
                try {
                    T result = fallbackFn.apply(fallback);
                    healthRegistry.recordSuccess(fallback);
                    return result;
                } catch (Exception ex) {
                    healthRegistry.recordFailure(fallback);
                    throw ex;
                }
            }

            throw e;
        }
    }

    private ProviderId selectFallback(Scenario scenario, ProviderId exclude) {
        List<ProviderId> priority = PRIORITY_MAP.getOrDefault(scenario,
            List.of(ProviderId.DEEPSEEK, ProviderId.KIMI, ProviderId.AGNESE));

        for (ProviderId provider : priority) {
            if (provider != exclude && healthRegistry.getHealthState(provider) == HealthState.HEALTHY) {
                return provider;
            }
        }
        return null;
    }
}
