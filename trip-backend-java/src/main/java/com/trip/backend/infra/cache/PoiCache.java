package com.trip.backend.infra.cache;

import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * POI 缓存（对应 Python poi_cache.py）
 * - key: poi:{city}:{category}:{queryHash}
 * - TTL: 3600s
 * - 仅 attraction / food 类别
 */
@Component
public class PoiCache {

    private final DualBackendCache cache;

    public PoiCache(DualBackendCache cache) {
        this.cache = cache;
    }

    public void put(String city, String category, String queryHash, String value) {
        String key = String.format("poi:%s:%s:%s", city, category, queryHash);
        cache.put(key, value, 3600, TimeUnit.SECONDS);
    }

    public Optional<String> get(String city, String category, String queryHash) {
        String key = String.format("poi:%s:%s:%s", city, category, queryHash);
        return cache.get(key);
    }

    public void invalidate(String city, String category) {
        // 简单实现：清空所有（生产环境应使用 pattern delete）
        // TODO: 实现 pattern delete（需 Redis SCAN + DELETE）
    }
}
