package com.trip.backend.infra.cache;

import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * Research Bundle 缓存（对应 Python research_bundle_cache.py）
 * - key: research_bundle:{city}:{budget_tier}:{days}d:{dep}:{interestsHash}
 * - TTL: 300s
 */
@Component
public class ResearchBundleCache {

    private final DualBackendCache cache;

    public ResearchBundleCache(DualBackendCache cache) {
        this.cache = cache;
    }

    public void put(String city, String budgetTier, int days, String departure, String interestsHash, String value) {
        String key = String.format("research_bundle:%s:%s:%dd:%s:%s",
            city, budgetTier, days, departure, interestsHash);
        cache.put(key, value, 300, TimeUnit.SECONDS);
    }

    public Optional<String> get(String city, String budgetTier, int days, String departure, String interestsHash) {
        String key = String.format("research_bundle:%s:%s:%dd:%s:%s",
            city, budgetTier, days, departure, interestsHash);
        return cache.get(key);
    }
}
