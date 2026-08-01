package com.trip.backend.infra.cache;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * 双后端缓存（Redis 优先，内存降级）
 */
public class DualBackendCache {

    private final CacheBackend<String> primary;
    private final CacheBackend<String> fallback;

    public DualBackendCache(CacheBackend<String> primary, CacheBackend<String> fallback) {
        this.primary = primary;
        this.fallback = fallback;
    }

    public void put(String key, String value) {
        primary.put(key, value);
        fallback.put(key, value);
    }

    public void put(String key, String value, long ttl, TimeUnit unit) {
        primary.put(key, value, ttl, unit);
        fallback.put(key, value, ttl, unit);
    }

    public Optional<String> get(String key) {
        Optional<String> result = primary.get(key);
        if (result.isPresent()) {
            return result;
        }
        return fallback.get(key);
    }

    public void delete(String key) {
        primary.delete(key);
        fallback.delete(key);
    }

    public boolean isAvailable() {
        return primary.isAvailable() || fallback.isAvailable();
    }
}
