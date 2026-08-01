package com.trip.backend.infra.cache;

import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * 工具缓存（对应 Python tool_cache.py）
 * - key: tool_cache:{tool}:{literalKey} 或 tool_cache:{tool}:embed:{text}
 * - TTL: 300-3600s（per-tool）
 */
@Component
public class ToolCache {

    private final DualBackendCache cache;

    public ToolCache(DualBackendCache cache) {
        this.cache = cache;
    }

    public void put(String tool, String key, String value, long ttlSeconds) {
        String cacheKey = "tool_cache:" + tool + ":" + key;
        cache.put(cacheKey, value, ttlSeconds, TimeUnit.SECONDS);
    }

    public Optional<String> get(String tool, String key) {
        String cacheKey = "tool_cache:" + tool + ":" + key;
        return cache.get(cacheKey);
    }

    /**
     * 构建字面 key（sorted keys + trim + lower）
     */
    public static String buildLiteralKey(String... parts) {
        return String.join(":", parts).trim().toLowerCase();
    }
}
