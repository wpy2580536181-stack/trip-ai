package com.trip.backend.service.agent.tools;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 工具结果缓存（对应 Python tool_cache.py）。
 *
 * 两种命中路径：
 * - 字面 key：sort keys + string trim/lower + city 类字段归一化（{a,b} == {b,a}）
 * - embedding key：算 query 向量，遍历已缓存向量找 cosine ≥ threshold（默认 0.85）
 *
 * 内存后端（无 Redis 依赖；Redis 接入留待后续，与 Python 语义对齐即可）。
 */
public class ToolCache {

    private static final List<String> CITY_FIELDS = List.of("city", "from_city", "to_city");

    private final long ttlMs;
    private final int maxSize;
    private final Map<String, Entry> store = new ConcurrentHashMap<>();

    private record Entry(String value, float[] vector, long createdAt) {}

    public ToolCache(long ttlSec, int maxSize) {
        this.ttlMs = ttlSec * 1000;
        this.maxSize = maxSize;
    }

    /** 构造字面 key：排序字段、跳过 null、字符串归一化。 */
    public String literalKey(String toolName, Map<String, Object> args) {
        Map<String, Object> normalized = new java.util.TreeMap<>();
        for (Map.Entry<String, Object> e : args.entrySet()) {
            Object v = e.getValue();
            if (v == null) {
                continue;
            }
            if (v instanceof String s) {
                v = s.trim().toLowerCase();
            }
            normalized.put(e.getKey(), v);
        }
        return rawKey(toolName, normalized);
    }

    private String rawKey(String toolName, Map<String, Object> normalized) {
        StringBuilder sb = new StringBuilder(toolName).append(":");
        boolean first = true;
        for (Map.Entry<String, Object> e : normalized.entrySet()) {
            if (!first) sb.append(',');
            sb.append(e.getKey()).append('=').append(e.getValue());
            first = false;
        }
        return sb.toString();
    }

    /** 字面 key 命中（TTL 内）。 */
    public synchronized String getLiteral(String key) {
        Entry e = store.get(key);
        if (e == null) {
            return null;
        }
        if (System.currentTimeMillis() - e.createdAt() > ttlMs) {
            store.remove(key);
            return null;
        }
        return e.value();
    }

    public synchronized void put(String key, String value, float[] vector) {
        if (store.size() >= maxSize) {
            // 简单淘汰：删最早一条
            store.entrySet().stream().min(Map.Entry.comparingByValue(
                java.util.Comparator.comparingLong(Entry::createdAt))).ifPresent(old -> store.remove(old.getKey()));
        }
        store.put(key, new Entry(value, vector, System.currentTimeMillis()));
    }

    /**
     * embedding 相似度命中：遍历缓存向量，返回 cosine ≥ threshold 的最近一条。
     * 前提：向量已 L2 normalize（与 Python 侧一致，等价点积）。
     */
    public synchronized String getByVector(float[] queryVec, double threshold) {
        if (queryVec == null) {
            return null;
        }
        String best = null;
        double bestSim = -1;
        long now = System.currentTimeMillis();
        for (Map.Entry<String, Entry> e : store.entrySet()) {
            Entry entry = e.getValue();
            if (entry.vector() == null || now - entry.createdAt() > ttlMs) {
                continue;
            }
            double sim = cosine(queryVec, entry.vector());
            if (sim >= threshold && sim > bestSim) {
                bestSim = sim;
                best = entry.value();
            }
        }
        return best;
    }

    private static double cosine(float[] a, float[] b) {
        double dot = 0;
        int n = Math.min(a.length, b.length);
        for (int i = 0; i < n; i++) {
            dot += a[i] * b[i];
        }
        return dot; // 双方均 L2 normalize → 点积即 cosine
    }

    /** 测试辅助：当前缓存条数。 */
    synchronized int size() {
        return store.size();
    }
}
