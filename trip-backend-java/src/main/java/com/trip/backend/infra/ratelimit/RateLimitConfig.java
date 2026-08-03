package com.trip.backend.infra.ratelimit;

import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 限流器配置（对应 Python RateLimitRegistry）
 * 6 个实例：
 * - global: 2000/60s
 * - auth: 1000/900s（E4测试临时放宽）
 * - chat: 200/60s
 * - recommend: 50/60s
 * - feedback: 30/3600s
 * - knowledge: 100/60s
 */
public enum RateLimitConfig {

    GLOBAL("global", 2000, 60),
    AUTH("auth", 1000, 900),  // E4测试临时：10->1000
    CHAT("chat", 200, 60),
    RECOMMEND("recommend", 50, 60),
    FEEDBACK("feedback", 30, 3600),
    KNOWLEDGE("knowledge", 100, 60);

    private final String name;
    private final int maxRequests;
    private final int windowSeconds;

    RateLimitConfig(String name, int maxRequests, int windowSeconds) {
        this.name = name;
        this.maxRequests = maxRequests;
        this.windowSeconds = windowSeconds;
    }

    public String getName() {
        return name;
    }

    public int getMaxRequests() {
        return maxRequests;
    }

    public int getWindowSeconds() {
        return windowSeconds;
    }
}
