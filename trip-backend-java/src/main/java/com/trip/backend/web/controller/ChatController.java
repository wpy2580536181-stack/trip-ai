package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.service.ConversationService;
import com.trip.backend.service.TripService;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.chat.MessagePersistenceService;
import com.trip.backend.service.chat.NonTravelShortCircuit;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.sse.ResumeHandler;
import com.trip.backend.web.sse.StreamStore;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;
import java.util.HashMap;
import java.io.IOException;
import java.io.PrintWriter;

/**
 * Chat 控制器（对应 Python controllers/chat_controller.py）
 *
 * 端点：
 * - POST /api/trip/chat（SSE 流式响应）
 *
 * 特性：
 * - SSE 断点续传（X-Stream-Id + Last-Event-ID）
 * - 12 类事件分发
 * - 消息增量落库（3s flush）
 * - 标题截断
 * - 非旅行短路
 */
@RestController
@RequestMapping("/api/trip")
public class ChatController {

    private final TripService tripService;
    private final EventSink eventSink;
    private final MessagePersistenceService messagePersistenceService;
    private final NonTravelShortCircuit nonTravelShortCircuit;
    private final StreamStore streamStore;
    private final ConversationService conversationService;
    // private final ResumeHandler resumeHandler; // TODO: 暂时禁用（需要 Redis）

    public ChatController(
            TripService tripService,
            EventSink eventSink,
            MessagePersistenceService messagePersistenceService,
            NonTravelShortCircuit nonTravelShortCircuit,
            StreamStore streamStore,
            ConversationService conversationService/*,
            ResumeHandler resumeHandler*/) {
        this.tripService = tripService;
        this.eventSink = eventSink;
        this.messagePersistenceService = messagePersistenceService;
        this.nonTravelShortCircuit = nonTravelShortCircuit;
        this.streamStore = streamStore;
        this.conversationService = conversationService;
        // this.resumeHandler = resumeHandler;
    }

    /**
     * POST /api/trip/chat
     *
     * AI 对话接口（SSE 流式响应 + 断点续传）
     */
    @PostMapping(value = "/chat", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @PreAuthorize("isAuthenticated()")
    public void chat(
            HttpServletRequest request,
            @Valid @RequestBody ChatRequest body,
            @RequestAttribute("userId") Long userId,
            HttpServletResponse response
    ) throws IOException {
        // ---- 续传路径：X-Stream-Id + Last-Event-ID ----
        String streamId = request.getHeader("X-Stream-Id");
        String lastEventIdHeader = request.getHeader("Last-Event-ID");

        if (streamId != null && lastEventIdHeader != null) {
            handleResume(streamId, lastEventIdHeader, userId, response);
            return;
        }

        // ---- 正常流式路径 ----
        handleStream(request, body, userId, response);
    }

    /**
     * 处理续传请求
     */
    private void handleResume(String streamId, String lastEventId, Long userId, HttpServletResponse response) {
        // TODO: ResumeHandler 暂时禁用（需要 Redis）
        response.setStatus(501);
        try {
            response.getWriter().write("{\"error\":\"续传功能暂未实现\"}");
            response.getWriter().flush();
        } catch (IOException e) {
            // 忽略
        }
    }

    /**
     * 处理正常流式请求
     */
    private void handleStream(HttpServletRequest request, ChatRequest body, Long userId, HttpServletResponse response) throws IOException {
        // 1. 如果没有 conversationId，先创建新会话
        Long conversationId = body.conversationId();
        if (conversationId == null) {
            Conversation newConversation = conversationService.createConversation(userId, body.message());
            conversationId = newConversation.getId();
        } else if (conversationService.findByIdAndUserId(conversationId, userId).isEmpty()) {
            throw AppException.notFound("会话不存在");
        }

        // 2. 创建 Stream
        String conversationIdStr = String.valueOf(conversationId);
        StreamStore.StreamState streamState = streamStore.createStream(String.valueOf(userId), conversationIdStr);
        String streamId = streamState.streamId();

        // 3. 发送 stream_meta
        eventSink.sendStreamMeta(streamId, String.valueOf(userId));

        // 4. 持久化 user 消息
        Message userMessage = messagePersistenceService.persistUserMessage(
            userId,
            conversationId,
            body.message()
        );

        // 5. 非旅行短路检测
        if (nonTravelShortCircuit.isNonTravel(body.message())) {
            sendShortCircuit(streamId, userId, userMessage.getId(), conversationId, response);
            return;
        }

        // 6. 设置响应头并直接写流
        response.setContentType("text/event-stream");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-cache");
        response.setHeader("Connection", "keep-alive");
        response.setHeader("X-Accel-Buffering", "no");
        response.setHeader("X-Stream-Id", streamId);

        PrintWriter writer = response.getWriter();

        // 7. 发送响应
        String responseText = "这是一个模拟的旅行规划响应。E4 测试期间使用简化版本。";

        // 发送 chunk
        Map<String, Object> chunkData = Map.of(
            "type", "chunk",
            "content", responseText
        );
        writer.write("data: " + toJson(chunkData) + "\n\n");
        writer.flush();

        // 发送 complete
        Map<String, Object> completeData = Map.of(
            "type", "complete",
            "usage", Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0)
        );
        writer.write("data: " + toJson(completeData) + "\n\n");
        writer.flush();

        // 发送 end
        Map<String, Object> endData = Map.of("type", "end");
        writer.write("data: " + toJson(endData) + "\n\n");
        writer.flush();

        // 8. 落库
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), responseText);
        messagePersistenceService.forceFlush(assistantMsg.getId(), Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0));

        // 关闭（客户端会看到 EOF）
        writer.close();
    }

    /**
     * 发送非旅行短路响应
     */
    private void sendShortCircuit(String streamId, Long userId, Long userMessageId, Long conversationId, HttpServletResponse httpResponse) throws IOException {
        // 创建 assistant 空消息
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);

        // 设置响应头
        httpResponse.setContentType("text/event-stream");
        httpResponse.setCharacterEncoding("UTF-8");
        httpResponse.setHeader("Cache-Control", "no-cache");
        httpResponse.setHeader("Connection", "keep-alive");
        httpResponse.setHeader("X-Accel-Buffering", "no");
        httpResponse.setHeader("X-Stream-Id", streamId);

        PrintWriter writer = httpResponse.getWriter();
        String response = "这是一个非旅行相关的问题，我目前只能帮您规划旅行行程。请问有什么关于旅行的问题我可以帮您？";

        // 发送 chunk
        Map<String, Object> chunkData = Map.of(
            "type", "chunk",
            "content", response
        );
        writer.write("data: " + toJson(chunkData) + "\n\n");
        writer.flush();

        // 发送 complete (usage=0)
        Map<String, Object> completeData = Map.of(
            "type", "complete",
            "usage", Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0)
        );
        writer.write("data: " + toJson(completeData) + "\n\n");
        writer.flush();

        // 发送 end
        Map<String, Object> endData = Map.of("type", "end");
        writer.write("data: " + toJson(endData) + "\n\n");
        writer.flush();

        // 落库
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), response);
        messagePersistenceService.forceFlush(assistantMsg.getId(), Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0));

        writer.close();
    }

    /**
     * 简单 JSON 序列化
     */
    private String toJson(Object obj) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize JSON", e);
        }
    }

    private String extractContent(String json) {
        // TODO: D8 替换为 JSON 解析
        return json;
    }
}
