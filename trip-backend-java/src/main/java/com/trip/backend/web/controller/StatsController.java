package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.TokenUsageLog;
import com.trip.backend.service.StatsService;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 统计控制器（对应 Python routers/stats.py）
 * 3 个端点：
 * - GET /api/stats/token-usage/summary
 * - GET /api/stats/token-usage/stats
 * - GET /api/stats/token-usage/logs
 */
@RestController
@RequestMapping("/api/stats")
public class StatsController {

    private final StatsService statsService;

    public StatsController(StatsService statsService) {
        this.statsService = statsService;
    }

    /**
     * GET /api/stats/token-usage/summary
     */
    @GetMapping("/token-usage/summary")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTokenUsageSummary(
            @RequestAttribute("userId") Long userId) {
        Map<String, Object> summary = statsService.getTokenUsageSummary(userId);
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", summary, "message", null, "error", null
        ));
    }

    /**
     * GET /api/stats/token-usage/stats
     */
    @GetMapping("/token-usage/stats")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTokenUsageStats(
            @RequestAttribute("userId") Long userId) {
        Map<String, Object> stats = statsService.getTokenUsageStats(userId);
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", stats, "message", null, "error", null
        ));
    }

    /**
     * GET /api/stats/token-usage/logs
     */
    @GetMapping("/token-usage/logs")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getTokenUsageLogs(
            @RequestAttribute("userId") Long userId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<TokenUsageLog> logs = statsService.getTokenUsageLogs(userId, page, pageSize);

        List<Map<String, Object>> items = logs.getContent().stream()
            .map(log -> Map.of(
                "id", log.getId(),
                "request_type", log.getRequestType(),
                "route", log.getRoute(),
                "prompt_tokens", log.getPromptTokens(),
                "completion_tokens", log.getCompletionTokens(),
                "total_tokens", log.getTotalTokens(),
                "cached_tokens", log.getCachedTokens(),
                "latency_ms", log.getLatencyMs(),
                "created_at", log.getCreatedAt().toString()
            ))
            .toList();

        Map<String, Object> data = Map.of(
            "items", items,
            "total", logs.getTotalElements(),
            "page", page,
            "pageSize", pageSize
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }
}
