package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.service.ConversationService;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 会话控制器（E4 测试最小实现）
 *
 * 端点：
 * - GET /api/conversations（列表）
 * - GET /api/conversations/{id}（详情）
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
     * 获取当前用户的会话列表
     */
    @GetMapping
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> listConversations(
            @RequestAttribute("userId") Long userId,
            HttpServletRequest httpRequest) {

        // TODO: ConversationService 需要实现 findByUserId 方法
        // 暂时返回空列表用于 E4 测试
        List<Conversation> conversations = List.of(); // conversationService.findByUserId(userId);

        Map<String, Object> data = new HashMap<>();
        data.put("items", conversations);
        data.put("total", 0);
        data.put("page", 1);
        data.put("pageSize", 20);

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            Map<String, Object> response = new HashMap<>();
            response.put("code", 200);
            response.put("data", data);
            response.put("message", null);
            response.put("error", null);
            return ResponseEntity.ok(response);
        }
    }

    /**
     * GET /api/conversations/{id}
     * 获取会话详情
     */
    @GetMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getConversation(
            @PathVariable Long id,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest httpRequest) {

        Conversation conversation = conversationService.findByIdAndUserId(id, userId)
            .orElseThrow(() -> AppException.notFound("会话不存在"));

        Map<String, Object> convData = new HashMap<>();
        convData.put("id", conversation.getId());
        convData.put("userId", conversation.getUserId());
        convData.put("title", conversation.getTitle());
        convData.put("createdAt", conversation.getCreatedAt());

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.ok(Map.of("success", true, "data", convData));
        } else {
            Map<String, Object> response = new HashMap<>();
            response.put("code", 200);
            response.put("data", convData);
            response.put("message", null);
            response.put("error", null);
            return ResponseEntity.ok(response);
        }
    }

    /**
     * DELETE /api/conversations/{id}
     * 删除会话（级联删除消息）
     */
    @DeleteMapping("/{id}")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> deleteConversation(
            @PathVariable Long id,
            @RequestAttribute("userId") Long userId,
            HttpServletRequest httpRequest) {

        conversationService.deleteConversation(userId, id);

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.ok(Map.of("success", true, "data", null));
        } else {
            return ResponseEntity.ok(Map.of("code", 200, "data", null, "message", null, "error", null));
        }
    }
}
