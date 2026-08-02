package com.trip.backend.middleware;

import java.util.ArrayList;
import java.util.List;

/**
 * Token 监控器（对应 Python token_monitor.py）
 * - 环形缓冲（1000 条）
 * - 单次 >100K 告警
 * - 统计信息
 */
public class TokenMonitor {

    private final int bufferSize;
    private final List<TokenUsage> buffer;
    private int index = 0;

    public TokenMonitor(int bufferSize) {
        this.bufferSize = bufferSize;
        this.buffer = new ArrayList<>(bufferSize);
    }

    /**
     * 记录 token 使用
     */
    public synchronized void record(TokenUsage usage) {
        if (buffer.size() < bufferSize) {
            buffer.add(usage);
        } else {
            buffer.set(index, usage);
        }
        index = (index + 1) % bufferSize;

        // 单次 >100K 告警
        if (usage.getTotalTokens() > 100_000) {
            System.err.printf("[TokenMonitor] ⚠️ 高 Token 消耗: userId=%d, totalTokens=%d, route=%s%n",
                usage.getUserId(), usage.getTotalTokens(), usage.getRoute());
        }
    }

    /**
     * 获取最近 N 条记录
     */
    public List<TokenUsage> getRecent(int n) {
        int size = buffer.size();
        if (n > size) n = size;

        List<TokenUsage> result = new ArrayList<>(n);
        int start = (index - n + size) % size;
        for (int i = 0; i < n; i++) {
            result.add(buffer.get((start + i) % size));
        }
        return result;
    }

    /**
     * 获取统计信息
     */
    public Stats getStats() {
        if (buffer.isEmpty()) {
            return new Stats(0, 0, 0, 0);
        }

        int total = buffer.stream().mapToInt(TokenUsage::getTotalTokens).sum();
        int avg = total / buffer.size();
        int max = buffer.stream().mapToInt(TokenUsage::getTotalTokens).max().orElse(0);

        return new Stats(
            buffer.size(),
            total,
            avg,
            max
        );
    }

    public record Stats(int count, int total, int avg, int max) {}
}
