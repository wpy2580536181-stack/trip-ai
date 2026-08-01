package com.trip.backend.service;

import com.trip.backend.domain.entity.TokenUsageLog;
import com.trip.backend.domain.repository.TokenUsageLogRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * 统计服务（对应 Python services/stats_service.py）
 */
@Service
public class StatsService {

    private final TokenUsageLogRepository tokenUsageLogRepository;

    public StatsService(TokenUsageLogRepository tokenUsageLogRepository) {
        this.tokenUsageLogRepository = tokenUsageLogRepository;
    }

    /**
     * 获取 Token 使用汇总
     */
    public Map<String, Object> getTokenUsageSummary(Long userId) {
        // 查询最近 1 小时的 token 使用
        OffsetDateTime oneHourAgo = OffsetDateTime.now().minusHours(1);
        var logs = tokenUsageLogRepository.findByUserIdAndRequestTypeAndCreatedAtBetween(
            userId, null, oneHourAgo, OffsetDateTime.now()
        );

        int current = logs.stream().mapToInt(TokenUsageLog::getTotalTokens).sum();
        int limit = 50000; // 用户每小时预算
        long resetAt = OffsetDateTime.now().plusHours(1).toInstant().toEpochMilli();

        return Map.of(
            "window", Map.of(
                "current", current,
                "limit", limit,
                "resetAt", resetAt
            ),
            "totalSinceStart", 0L // TODO: 实现全量统计
        );
    }

    /**
     * 获取 Token 使用统计
     */
    public Map<String, Object> getTokenUsageStats(Long userId) {
        OffsetDateTime oneHourAgo = OffsetDateTime.now().minusHours(1);
        var logs = tokenUsageLogRepository.findByUserIdAndRequestTypeAndCreatedAtBetween(
            userId, null, oneHourAgo, OffsetDateTime.now()
        );

        int current = logs.stream().mapToInt(TokenUsageLog::getTotalTokens).sum();
        int limit = 50000;

        return Map.of(
            "window", Map.of(
                "current", current,
                "limit", limit,
                "resetAt", OffsetDateTime.now().plusHours(1).toInstant().toEpochMilli()
            ),
            "totalSinceStart", 0L
        );
    }

    /**
     * 获取 Token 使用日志
     */
    public Page<TokenUsageLog> getTokenUsageLogs(Long userId, int page, int pageSize) {
        return tokenUsageLogRepository.findByUserIdOrderByCreatedAtDesc(
            userId, PageRequest.of(page - 1, pageSize)
        );
    }

    /**
     * 获取 Agent 执行轨迹
     */
    public List<Map<String, Object>> getAgentTrace(Long messageId) {
        // TODO: 从 agent_steps 查询
        return List.of();
    }

    /**
     * 按会话 ID 获取 Agent 执行轨迹
     */
    public List<Map<String, Object>> getAgentTraceByConversationId(Long conversationId, int limit) {
        // TODO: 实现
        return List.of();
    }

    /**
     * 获取 MCP 指标快照
     */
    public Map<String, Object>> getMcpStats() {
        // TODO: 从 MCP 指标收集器获取
        return Map.of(
            "calls", 0,
            "successes", 0,
            "failures", 0,
            "cacheHits", 0,
            "circuitOpenCount", 0,
            "avgDurationMs", 0.0
        );
    }
}
