package com.trip.backend.web.controller;

import com.trip.backend.service.StatsService;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 管理后台控制器（对应 Python routers/admin.py）
 * 3 个端点：
 * - GET /api/admin/agent-trace/{message_id}
 * - GET /api/admin/agent-trace（conversation_id + limit）
 * - GET /api/admin/mcp-stats
 */
@RestController
@RequestMapping("/api/admin")
public class AdminController {

    private final StatsService statsService;

    public AdminController(StatsService statsService) {
        this.statsService = statsService;
    }

    /**
     * GET /api/admin/agent-trace/{message_id}
     */
    @GetMapping("/agent-trace/{message_id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getAgentTrace(@PathVariable("message_id") Long messageId) {
        List<Map<String, Object>> trace = statsService.getAgentTrace(messageId);
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", trace, "message", null, "error", null
        ));
    }

    /**
     * GET /api/admin/agent-trace（conversation_id + limit）
     */
    @GetMapping("/agent-trace")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getAgentTraceByConversation(
            @RequestParam(required = false) Long conversation_id,
            @RequestParam(defaultValue = "10") int limit) {
        if (conversation_id == null) {
            return ResponseEntity.badRequest().body(Map.of(
                "code", 400, "data", null, "message", "conversation_id 必填", "error", "bad_request"
            ));
        }

        List<Map<String, Object>> trace = statsService.getAgentTraceByConversationId(conversation_id, limit);
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", trace, "message", null, "error", null
        ));
    }

    /**
     * GET /api/admin/mcp-stats
     */
    @GetMapping("/mcp-stats")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getMcpStats() {
        Map<String, Object> stats = statsService.getMcpStats();
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", stats, "message", null, "error", null
        ));
    }
}
