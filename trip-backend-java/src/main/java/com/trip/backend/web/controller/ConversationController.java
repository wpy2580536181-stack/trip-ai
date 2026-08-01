package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Message;
import com.trip.backend.service.ConversationService;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 会话控制器（对应 Python routers/conversation.py）
 * 4 个端点：
 * - GET /api/conversations（分页）
 * - GET /api/conversations/{id}（详情 + 消息）
 * - POST /api/conversations
 * - DELETE /api/conversations/{id}
 */
@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    /**
     * GET /api/conversations
     */
    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getConversations(
            @RequestAttribute("userId") Long userId,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int pageSize) {
        Page<com.trip.backend.domain.entity.Conversation> conversations =
            conversationService.getConversations(userId, page, pageSize);

        Map<String, Object> data = Map.of(
            "items", conversations.getContent(),
            "total", conversations.getTotalElements(),
            "page", page,
            "pageSize", pageSize
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * GET /api/conversations/{id}
     */
    @GetMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getConversation(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        ConversationService.ConversationWithMessages cwm =
            conversationService.getConversation(userId, id);

        // 转换 Message 为 snake_case（匹配 Python 返回格式）
        List<Map<String, Object>> messages = cwm.messages().stream()
            .map(msg -> Map.of(
                "id", msg.getId(),
                "role", msg.getRole(),
                "content", msg.getContent(),
                "metadata", msg.getMetadata(),
                "created_at", msg.getCreatedAt().toString()
            ))
            .toList();

        Map<String, Object> data = Map.of(
            "id", cwm.conversation().getId(),
            "title", cwm.conversation().getTitle(),
            "messages", messages
        );

        return ResponseEntity.ok(Map.of(
            "code", 200, "data", data, "message", null, "error", null
        ));
    }

    /**
     * POST /api/conversations
     */
    @PostMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> createConversation(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody(required = false) CreateRequest request) {
        String title = request != null ? request.title() : null;
        var conversation = conversationService.createConversation(userId, title);

        Map<String, Object> data = Map.of(
            "id", conversation.getId(),
            "title", conversation.getTitle()
        );

        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
            "code", 201, "data", data, "message", null, "error", null
        ));
    }

    /**
     * DELETE /api/conversations/{id}
     */
    @DeleteMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> deleteConversation(
            @RequestAttribute("userId") Long userId,
            @PathVariable Long id) {
        conversationService.deleteConversation(userId, id);
        return ResponseEntity.noContent().build();
    }

    public record CreateRequest(@NotBlank String title) {}
}
