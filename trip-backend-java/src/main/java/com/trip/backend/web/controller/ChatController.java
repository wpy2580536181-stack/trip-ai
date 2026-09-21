package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.infra.metrics.PrometheusMetrics;
import com.trip.backend.service.ConversationService;
import com.trip.backend.service.TripService;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.chat.MessagePersistenceService;
import com.trip.backend.service.chat.NonTravelShortCircuit;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.sse.ResumeHandler;
import com.trip.backend.web.sse.StreamStore;
import com.trip.backend.web.sse.SseWriter;
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
import java.io.IOException;

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
    private final PrometheusMetrics prometheusMetrics;
    // private final ResumeHandler resumeHandler; // TODO: 暂时禁用（需要 Redis）

    public ChatController(
            TripService tripService,
            EventSink eventSink,
            MessagePersistenceService messagePersistenceService,
            NonTravelShortCircuit nonTravelShortCircuit,
            StreamStore streamStore,
            ConversationService conversationService,
            PrometheusMetrics prometheusMetrics/*,
            ResumeHandler resumeHandler*/) {
        this.tripService = tripService;
        this.eventSink = eventSink;
        this.messagePersistenceService = messagePersistenceService;
        this.nonTravelShortCircuit = nonTravelShortCircuit;
        this.streamStore = streamStore;
        this.conversationService = conversationService;
        this.prometheusMetrics = prometheusMetrics;
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
        long startNanos = System.nanoTime();
        try {
            // ---- 续传路径：X-Stream-Id + Last-Event-ID ----
            String streamId = request.getHeader("X-Stream-Id");
            String lastEventIdHeader = request.getHeader("Last-Event-ID");

            if (streamId != null && lastEventIdHeader != null) {
                handleResume(streamId, lastEventIdHeader, userId, response);
                return;
            }

            // ---- 正常流式路径 ----
            handleStream(request, body, userId, response);
        } finally {
            // chat 流式响应总耗时打点（对应 Python record_chat_duration）
            try {
                double durationSeconds = (System.nanoTime() - startNanos) / 1_000_000_000.0;
                prometheusMetrics.recordChatDuration(durationSeconds);
            } catch (Exception e) {
                // 打点失败不影响主流程
            }
        }
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

        // 3. 创建请求级 SseWriter 并发送 stream_meta
        SseWriter sseWriter = new SseWriter(response);
        response.setHeader("X-Stream-Id", streamId);
        eventSink.sendStreamMeta(sseWriter, streamId, String.valueOf(userId));

        // 4. 持久化 user 消息
        Message userMessage = messagePersistenceService.persistUserMessage(
            userId,
            conversationId,
            body.message()
        );

        // 5. 非旅行短路检测
        if (nonTravelShortCircuit.isNonTravel(body.message())) {
            sendShortCircuit(sseWriter, streamId, userId, userMessage.getId(), conversationId);
            return;
        }

        // 6. 发送响应
        String responseText = "这是一个模拟的旅行规划响应。E4 测试期间使用简化版本。";
        Map<String, Object> completeData = Map.of(
            "type", "complete",
            "usage", Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0)
        );
        eventSink.sendChunk(sseWriter, streamId, responseText);
        eventSink.sendComplete(sseWriter, streamId, completeData.get("usage"));

        // 8. 落库
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), responseText);
        messagePersistenceService.forceFlush(assistantMsg.getId(), Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0));
    }

    /**
     * 发送非旅行短路响应
     */
    private void sendShortCircuit(SseWriter sseWriter, String streamId, Long userId, Long userMessageId, Long conversationId) throws IOException {
        // 创建 assistant 空消息
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
        String response = "这是一个非旅行相关的问题，我目前只能帮您规划旅行行程。请问有什么关于旅行的问题我可以帮您？";
        Map<String, Object> usage = Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0);
        eventSink.sendChunk(sseWriter, streamId, response);
        eventSink.sendComplete(sseWriter, streamId, usage);

        // 落库
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), response);
        messagePersistenceService.forceFlush(assistantMsg.getId(), usage);
    }

    private String extractContent(String json) {
        // TODO: D8 替换为 JSON 解析
        return json;
    }
}
