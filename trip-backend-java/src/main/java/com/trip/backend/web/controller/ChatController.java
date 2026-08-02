package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.service.TripService;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.chat.MessagePersistenceService;
import com.trip.backend.service.chat.NonTravelShortCircuit;
import com.trip.backend.web.sse.ResumeHandler;
import com.trip.backend.web.sse.StreamStore;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;

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
    private final ResumeHandler resumeHandler;

    public ChatController(
            TripService tripService,
            EventSink eventSink,
            MessagePersistenceService messagePersistenceService,
            NonTravelShortCircuit nonTravelShortCircuit,
            StreamStore streamStore,
            ResumeHandler resumeHandler) {
        this.tripService = tripService;
        this.eventSink = eventSink;
        this.messagePersistenceService = messagePersistenceService;
        this.nonTravelShortCircuit = nonTravelShortCircuit;
        this.streamStore = streamStore;
        this.resumeHandler = resumeHandler;
    }

    /**
     * POST /api/trip/chat
     *
     * AI 对话接口（SSE 流式响应 + 断点续传）
     */
    @PostMapping(value = "/chat", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<SseEmitter> chat(
            HttpServletRequest request,
            @Valid @RequestBody ChatRequest body,
            @RequestAttribute("userId") Long userId
    ) {
        // ---- 续传路径：X-Stream-Id + Last-Event-ID ----
        String streamId = request.getHeader("X-Stream-Id");
        String lastEventIdHeader = request.getHeader("Last-Event-ID");

        if (streamId != null && lastEventIdHeader != null) {
            return handleResume(streamId, lastEventIdHeader, userId);
        }

        // ---- 正常流式路径 ----
        return handleStream(request, body, userId);
    }

    /**
     * 处理续传请求
     */
    private ResponseEntity<SseEmitter> handleResume(String streamId, String lastEventId, Long userId) {
        try {
            long lastSeq = Long.parseLong(lastEventId);
            if (lastSeq < 0) {
                return createErrorResponse(400, "Last-Event-ID 必须是非负整数");
            }

            ResumeHandler.ResumeResult result = resumeHandler.handleResumeWithAuth(streamId, lastSeq, userId);

            SseEmitter emitter = new SseEmitter(60_000L); // 60s 超时
            new Thread(() -> {
                try {
                    for (var event : result.events()) {
                        emitter.send(SseEmitter.event()
                            .id(String.valueOf(event.seq()))
                            .name(event.type())
                            .data(event.data()));
                    }
                    // 追加 end 帧
                    emitter.send(SseEmitter.event()
                        .id(String.valueOf(result.totalSeq() + 1))
                        .name("end")
                        .data("{}"));
                    emitter.complete();
                } catch (Exception e) {
                    emitter.completeWithError(e);
                }
            }).start();

            return ResponseEntity.ok(emitter);

        } catch (NumberFormatException e) {
            return createErrorResponse(400, "Last-Event-ID 必须是非负整数");
        } catch (ResumeHandler.ResumeException e) {
            return createErrorResponse(e.getStatusCode(), e.getMessage());
        }
    }

    /**
     * 处理正常流式请求
     */
    private ResponseEntity<SseEmitter> handleStream(HttpServletRequest request, ChatRequest body, Long userId) {
        // 1. 创建 Stream
        String conversationId = body.conversationId() != null
            ? String.valueOf(body.conversationId())
            : "pending";

        StreamStore.StreamState streamState = streamStore.createStream(String.valueOf(userId), conversationId);
        String streamId = streamState.streamId();

        // 2. 发送 stream_meta
        eventSink.sendStreamMeta(streamId, String.valueOf(userId));

        // 3. 持久化 user 消息
        Message userMessage = messagePersistenceService.persistUserMessage(
            userId,
            body.conversationId() != null ? body.conversationId() : null, // TODO: 创建新会话
            body.message()
        );

        // 4. 非旅行短路检测
        if (nonTravelShortCircuit.isNonTravel(body.message())) {
            return sendShortCircuit(streamId, userId, userMessage.getId());
        }

        // 5. 创建 SseEmitter
        SseEmitter emitter = new SseEmitter(0L); // 0L = 不超时（由 SseWriter 控制）

        // 6. 启动消费线程（D8 前暂时直接返回 emitter，后续接入真实 SseWriter）
        // TODO: D8 接入 SseWriter + EventSink

        // 7. 返回响应（含 X-Stream-Id）
        return ResponseEntity.ok()
            .header("X-Stream-Id", streamId)
            .header("Cache-Control", "no-cache")
            .header("Connection", "keep-alive")
            .header("X-Accel-Buffering", "no")
            .body(emitter);
    }

    /**
     * 发送非旅行短路响应
     */
    private ResponseEntity<SseEmitter> sendShortCircuit(String streamId, Long userId, Long userMessageId) {
        // 创建 assistant 空消息
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, null);

        SseEmitter emitter = new SseEmitter(0L);

        new Thread(() -> {
            try {
                sseWriter.attach(emitter);

                // 发送短路响应
                String response = "这是一个非旅行相关的问题，我目前只能帮您规划旅行行程。请问有什么关于旅行的问题我可以帮您？";

                // chunk
                emitter.send(SseEmitter.event()
                    .name("chunk")
                    .data(Map.of("content", response)));

                // complete (usage=0)
                emitter.send(SseEmitter.event()
                    .name("complete")
                    .data(Map.of("usage", Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0))));

                // end
                emitter.send(SseEmitter.event()
                    .name("end")
                    .data("{}"));

                // 落库
                messagePersistenceService.appendAssistantContent(assistantMsg.getId(), response);
                messagePersistenceService.forceFlush(assistantMsg.getId(), Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0));

                emitter.complete();
            } catch (Exception e) {
                try {
                    emitter.completeWithError(e);
                } catch (Exception ex) {
                    // 忽略
                }
            }
        }).start();

        return ResponseEntity.ok()
            .header("X-Stream-Id", streamId)
            .header("Cache-Control", "no-cache")
            .header("Connection", "keep-alive")
            .header("X-Accel-Buffering", "no")
            .body(emitter);
    }

    /**
     * 创建错误响应（SSE 格式）
     */
    private ResponseEntity<SseEmitter> createErrorResponse(int status, String error) {
        SseEmitter emitter = new SseEmitter();
        try {
            emitter.send(SseEmitter.event()
                .name("error")
                .data(Map.of("error", error)));
            emitter.complete();
        } catch (Exception e) {
            emitter.completeWithError(e);
        }
        return ResponseEntity.status(status).body(emitter);
    }

    private String extractContent(String json) {
        // TODO: D8 替换为 JSON 解析
        return json;
    }
}
