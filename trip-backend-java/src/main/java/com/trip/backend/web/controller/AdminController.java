package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.AgentStep;
import com.trip.backend.service.AdminService;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Admin controller（管理后台）
 *
 * 端点：
 * - GET /api/admin/agent-trace/{messageId}（获取 Agent 执行轨迹）
 * - GET /api/admin/agent-trace（获取 Agent 执行轨迹摘要列表）
 * - GET /api/admin/mcp-stats（获取 MCP 进程状态和调用指标）
 */
@RestController
@RequestMapping("/api/admin")
@Validated
public class AdminController {

    private final AdminService adminService;

    public AdminController(AdminService adminService) {
        this.adminService = adminService;
    }

    /**
     * GET /api/admin/agent-trace/{messageId}
     *
     * 获取 Agent 执行轨迹
     */
    @GetMapping("/agent-trace/{messageId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getAgentTrace(
            @PathVariable Long messageId,
            HttpServletRequest request) {

        List<AgentStep> steps = adminService.getAgentTrace(messageId);

        List<Map<String, Object>> stepList = steps.stream()
            .map(step -> {
                Map<String, Object> item = new HashMap<>();
                item.put("id", step.getId());
                item.put("step", step.getStep());
                item.put("stepName", step.getStepName());
                item.put("stepType", step.getStepType());
                item.put("status", step.getStatus());
                item.put("output", step.getOutput());
                item.put("durationMs", step.getDurationMs());
                item.put("error", step.getError());
                item.put("createdAt", step.getCreatedAt());
                return item;
            })
            .toList();

        Map<String, Object> data = new HashMap<>();
        data.put("steps", stepList);

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", data) :
            Map.of("code", 200, "data", data, "message", "获取成功", "error", null)
        );
    }

    /**
     * GET /api/admin/agent-trace
     *
     * 获取 Agent 执行轨迹摘要列表
     */
    @GetMapping("/agent-trace")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getAgentTraceSummary(
            @RequestParam Long conversation_id,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit,
            HttpServletRequest request) {

        List<Map<String, Object>> summaries = adminService.getAgentTraceSummary(conversation_id, limit);

        Map<String, Object> data = new HashMap<>();
        data.put("summaries", summaries);

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", data) :
            Map.of("code", 200, "data", data, "message", "获取成功", "error", null)
        );
    }

    /**
     * GET /api/admin/mcp-stats
     *
     * 获取 MCP 进程状态和调用指标
     */
    @GetMapping("/mcp-stats")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getMcpStats(HttpServletRequest request) {

        Map<String, Object> stats = adminService.getMcpStats();

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", stats) :
            Map.of("code", 200, "data", stats, "message", "获取成功", "error", null)
        );
    }
}
