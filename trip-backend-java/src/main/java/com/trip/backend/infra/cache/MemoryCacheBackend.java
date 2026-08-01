package com.trip.backend.infra.cache;

import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 内存缓存后端（降级用）
 */
public class MemoryCacheBackend implements CacheBackend<String> {

    private final ConcurrentHashMap<String, Entry> cache = new ConcurrentHashMap<>();
    private final int maxSize;

    public MemoryCacheBackend(int maxSize) {
        this.maxSize = maxSize;
    }

    @Override
    public void put(String key, String value) {
        cache.put(key, new Entry(value, Instant.now().plusSeconds(3600)));
    }

    @Override
    public void put(String key, String value, long ttl, TimeUnit unit) {
        cache.put(key, new Entry(value, Instant.now().plusSeconds(unit.toSeconds(ttl))));
    }

    @Override
    public Optional<String> get(String key) {
        Entry entry = cache.get(key);
        if (entry == null) {
            return Optional.empty();
        }
        if (Instant.now().isAfter(entry.expiresAt)) {
            cache.remove(key);
            return Optional.empty();
        }
        return Optional.of(entry.value);
    }

    @Override
    public void delete(String key) {
        cache.remove(key);
    }

    @Override
    public void clear() {
        cache.clear();
    }

    @Override
    public boolean isAvailable() {
        return true;
    }

    private static class Entry {
        String value;
        Instant expiresAt;

        Entry(String value, Instant expiresAt) {
            this.value = value;
            this.expiresAt = expiresAt;
        }
    }
}
