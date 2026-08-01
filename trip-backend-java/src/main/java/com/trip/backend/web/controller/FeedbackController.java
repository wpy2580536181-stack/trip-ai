package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Feedback;
import com.trip.backend.service.FeedbackService;
import com.trip.backend.utils.AppException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 反馈控制器（对应 Python routers/feedback.py）
 * 10 个端点：
 * - GET /api/feedback
 * - POST /api/feedback
 * - GET /api/feedback/message/{message_id}（公开）
 * - GET /api/feedback/stats
 * - GET /api/feedback/list/{message_id}（公开）
 * - GET /api/feedback/admin/high-token-low-satisfaction（Admin）
 * - GET /api/feedback/admin/daily-stats（Admin）
 * - POST /api/feedback/admin/test-alert（Admin）
 * - POST /api/feedback/admin/convert-to-fixture（Admin）
 */
@RestController
@RequestMapping("/api/feedback")
public class FeedbackController {

    private final FeedbackService feedbackService;

    public FeedbackController(FeedbackService feedbackService) {
        this.feedbackService = feedbackService;
    }

    /**
     * GET /api/feedback
     */
    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getFeedbacks(
            @RequestAttribute("userId") Long userId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<Feedback> feedbacks = feedbackService.getFeedbackByMessageId(userId, page, pageSize);

        List<Map<String, Object>> items = feedbacks.getContent().stream()
            .map(fb -> Map.of(
                "id", fb.getId(),
                "message_id", fb.getMessageId(),
                "rating", fb.getRating(),
                "comment", fb.getComment(),
                "tags", fb.getTags(),
                "created_at", fb.getCreatedAt().toString()
            ))
            .toList();

        Map<String, Object> data = Map.of(
            "items", items,
            "total", feedbacks.getTotalElements(),
            "page", page,
            "pageSize", pageSize
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * POST /api/feedback
     */
    @PostMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> submitFeedback(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody SubmitFeedbackRequest request) {
        Feedback feedback = feedbackService.submitFeedback(
            userId, request.messageId(), request.rating(), request.comment(), request.tags()
        );

        Map<String, Object> data = Map.of(
            "id", feedback.getId(),
            "rating", feedback.getRating()
        );

        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
            "code", 201, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/feedback/message/{message_id}（公开）
     */
    @GetMapping("/message/{message_id}")
    public ResponseEntity<Map<String, Object>> getFeedbackByMessageId(
            @PathVariable("message_id") Long messageId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<Feedback> feedbacks = feedbackService.getFeedbackByMessageId(messageId, page, pageSize);

        List<Map<String, Object>> items = feedbacks.getContent().stream()
            .map(fb -> Map.of(
                "id", fb.getId(),
                "rating", fb.getRating(),
                "comment", fb.getComment(),
                "created_at", fb.getCreatedAt().toString()
            ))
            .toList();

        Map<String, Object> data = Map.of(
            "items", items,
            "total", feedbacks.getTotalElements()
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/feedback/stats
     */
    @GetMapping("/stats")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getStats() {
        Map<String, Object> stats = feedbackService.getFeedbackStats();
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", stats, "message", null, "error", null
        ));
    }

    /**
     * GET /api/feedback/list/{message_id}（公开）
     */
    @GetMapping("/list/{message_id}")
    public ResponseEntity<Map<String, Object>> getFeedbackList(@PathVariable("message_id") Long messageId) {
        List<Feedback> feedbacks = feedbackService.getFeedbackListByMessageId(messageId);

        List<Map<String, Object>> items = feedbacks.stream()
            .map(fb -> Map.of(
                "id", fb.getId(),
                "rating", fb.getRating(),
                "comment", fb.getComment()
            ))
            .toList();

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", items, "message", null, "error", null
        ));
    }

    /**
     * GET /api/feedback/admin/high-token-low-satisfaction（Admin）
     */
    @GetMapping("/admin/high-token-low-satisfaction")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getHighTokenLowSatisfaction() {
        List<Map<String, Object>> cases = feedbackService.getHighTokenLowSatisfaction();
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", cases, "message", null, "error", null
        ));
    }

    /**
     * GET /api/feedback/admin/daily-stats（Admin）
     */
    @GetMapping("/admin/daily-stats")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> getDailyStats() {
        List<Map<String, Object>> stats = feedbackService.getDailyStats();
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", stats, "message", null, "error", null
        ));
    }

    /**
     * POST /api/feedback/admin/test-alert（Admin）
     */
    @PostMapping("/admin/test-alert")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> testAlert() {
        feedbackService.testAlert();
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", Map.of("alert", "triggered"), "message", null, "error", null
        ));
    }

    /**
     * POST /api/feedback/admin/convert-to-fixture（Admin）
     */
    @PostMapping("/admin/convert-to-fixture/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> convertToFixture(@PathVariable Long id) {
        feedbackService.convertToFixture(id);
        return ResponseEntity.ok(Map.of(
            "code", 200, "data", Map.of("converted", true), "message", null, "error", null
        ));
    }

    // ========== DTOs ==========

    public record SubmitFeedbackRequest(
        Integer rating, // 手动校验：1 或 -1
        @Size(max = 500) String comment,
        @Size(max = 10) List<String> tags,
        Long messageId
    ) {}
}
