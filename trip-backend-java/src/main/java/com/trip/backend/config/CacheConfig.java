package com.trip.backend.config;

import com.trip.backend.infra.cache.CacheBackend;
import com.trip.backend.infra.cache.DualBackendCache;
import com.trip.backend.infra.cache.MemoryCacheBackend;
import com.trip.backend.middleware.TokenBudgetManager;
import com.trip.backend.middleware.TokenMonitor;
import com.trip.backend.service.llm.ProviderConfig;
import com.trip.backend.service.llm.ProviderHealthRegistry;
import com.trip.backend.service.llm.ProviderRouter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

/**
 * 应用配置（简化版 - 用于无 Docker 环境启动）
 */
@Configuration
public class CacheConfig {

    @Bean
    public RestTemplate restTemplate() {
        return new RestTemplate();
    }

    @Bean
    public ProviderHealthRegistry providerHealthRegistry() {
        return new ProviderHealthRegistry();
    }

    @Bean
    public ProviderRouter providerRouter(ProviderConfig providerConfig, ProviderHealthRegistry healthRegistry) {
        return new ProviderRouter(providerConfig, healthRegistry);
    }

    @Bean
    public DualBackendCache dualBackendCache() {
        CacheBackend<String> memoryCache = new MemoryCacheBackend(1000);
        CacheBackend<String> memoryCache2 = new MemoryCacheBackend(1000);
        return new DualBackendCache(memoryCache, memoryCache2);
    }

    @Bean
    public TokenMonitor tokenMonitor() {
        return new TokenMonitor(1000);
    }

    @Bean
    public TokenBudgetManager tokenBudgetManager() {
        return new TokenBudgetManager(50000, 1, 200000, 1);
    }
}
