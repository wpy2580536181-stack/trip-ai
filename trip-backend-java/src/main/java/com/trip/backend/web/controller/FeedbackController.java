package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Feedback;
import com.trip.backend.service.FeedbackService;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Feedback controller（简化版）
 *
 * 端点：
 * - GET /api/feedback（获取反馈列表）
 * - POST /api/feedback（提交反馈）
 * - GET /api/feedback/message/{id}（获取消息反馈统计）
 * - GET /api/feedback/stats（获取全局统计，admin）
 * - GET /api/feedback/list/{id}（获取消息反馈列表，admin）
 */
@RestController
@RequestMapping("/api/feedback")
@Validated
public class FeedbackController {

    private final FeedbackService feedbackService;

    public FeedbackController(FeedbackService feedbackService) {
        this.feedbackService = feedbackService;
    }

    /**
     * GET /api/feedback
     *
     * 获取反馈列表
     */
    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getFeedbacks(
            @RequestAttribute("userId") Long userId,
            @RequestParam(name = "page", defaultValue = "1") @Min(1) int page,
            @RequestParam(name = "pageSize", defaultValue = "20") @Min(1) @Max(100) int pageSize,
            HttpServletRequest request) {

        Page<Feedback> feedbackPage = feedbackService.getUserFeedbacks(userId, page, pageSize);

        List<Map<String, Object>> items = feedbackPage.getContent().stream()
            .map(fb -> {
                Map<String, Object> item = new HashMap<>();
                item.put("id", fb.getId());
                item.put("messageId", fb.getMessageId());
                item.put("conversationId", fb.getConversationId());
                item.put("rating", fb.getRating());
                item.put("comment", fb.getComment());
                item.put("tags", fb.getTags());
                item.put("createdAt", fb.getCreatedAt());
                return item;
            })
            .toList();

        Map<String, Object> data = new HashMap<>();
        data.put("items", items);
        data.put("total", feedbackPage.getTotalElements());
        data.put("page", page);
        data.put("pageSize", pageSize);

        if (FormatResolver.isFormatA(request)) {
            Map<String,Object> env = new HashMap<>();
            env.put("success", true); env.put("data", data);
            return ResponseEntity.ok(env);
        }
        Map<String,Object> env = new HashMap<>();
        env.put("code", 200); env.put("data", data);
        env.put("message", "获取成功"); env.put("error", null);
        return ResponseEntity.ok(env);
    }

    /**
     * POST /api/feedback
     *
     * 提交反馈
     */
    @PostMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> submitFeedback(
            @RequestBody Map<String, Object> feedbackData,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest request) {

        Long messageId = feedbackData.get("messageId") == null
            ? null
            : ((Number) feedbackData.get("messageId")).longValue();
        Long conversationId = feedbackData.get("conversationId") == null
            ? null
            : ((Number) feedbackData.get("conversationId")).longValue();
        Integer rating = (Integer) feedbackData.get("rating");
        String comment = (String) feedbackData.get("comment");
        java.util.List<String> tags = (java.util.List<String>) feedbackData.get("tags");

        Feedback feedback = feedbackService.submitFeedback(
            userId, messageId, conversationId, rating, comment, tags
        );

        Map<String, Object> data = new HashMap<>();
        data.put("id", feedback.getId());
        data.put("rating", feedback.getRating());

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", data) :
            Map.of("code", 200, "data", data, "message", "反馈提交成功", "error", null)
        );
    }

    /**
     * GET /api/feedback/message/{messageId}
     *
     * 获取消息反馈统计
     */
    @GetMapping("/message/{messageId}")
    public ResponseEntity<Map<String, Object>> getMessageStats(
            @PathVariable Long messageId,
            HttpServletRequest request) {

        Map<String, Object> stats = feedbackService.getMessageStats(messageId);

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", stats) :
            Map.of("code", 200, "data", stats, "message", "获取成功", "error", null)
        );
    }

    /**
     * GET /api/feedback/stats
     *
     * 获取全局反馈统计（admin）
     */
    @GetMapping("/stats")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getGlobalStats(
            @RequestParam(name = "days", defaultValue = "7") @Min(1) @Max(90) int days,
            HttpServletRequest request) {

        Map<String, Object> stats = feedbackService.getGlobalStats(days);

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", stats) :
            Map.of("code", 200, "data", stats, "message", "获取成功", "error", null)
        );
    }

    /**
     * GET /api/feedback/list/{messageId}
     *
     * 获取消息反馈列表（admin）
     */
    @GetMapping("/list/{messageId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> listForMessage(
            @PathVariable Long messageId,
            HttpServletRequest request) {

        List<Map<String, Object>> feedbacks = feedbackService.listForMessage(messageId);

        return ResponseEntity.ok(FormatResolver.isFormatA(request) ?
            Map.of("success", true, "data", feedbacks) :
            Map.of("code", 200, "data", feedbacks, "message", "获取成功", "error", null)
        );
    }
}
