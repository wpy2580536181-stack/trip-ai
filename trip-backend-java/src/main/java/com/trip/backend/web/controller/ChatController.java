package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.infra.metrics.PrometheusMetrics;
import com.trip.backend.service.ConversationService;
import com.trip.backend.service.TripService;
import com.trip.backend.service.agent.ChatAgent;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.chat.MessagePersistenceService;
import com.trip.backend.service.chat.NonTravelShortCircuit;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.sse.ResumeHandler;
import com.trip.backend.web.sse.SseEvent;
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

import java.util.ArrayList;
import java.util.List;
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
    private final ResumeHandler resumeHandler;
    private final ChatAgent chatAgent;

    public ChatController(
            TripService tripService,
            EventSink eventSink,
            MessagePersistenceService messagePersistenceService,
            NonTravelShortCircuit nonTravelShortCircuit,
            StreamStore streamStore,
            ConversationService conversationService,
            PrometheusMetrics prometheusMetrics,
            ResumeHandler resumeHandler,
            ChatAgent chatAgent) {
        this.tripService = tripService;
        this.eventSink = eventSink;
        this.messagePersistenceService = messagePersistenceService;
        this.nonTravelShortCircuit = nonTravelShortCircuit;
        this.streamStore = streamStore;
        this.conversationService = conversationService;
        this.prometheusMetrics = prometheusMetrics;
        this.resumeHandler = resumeHandler;
        this.chatAgent = chatAgent;
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
     * 处理续传请求（断点续传）
     * 只读重放 seq > lastSeq 的全部事件，保留原 id，不写入 StreamStore
     */
    private void handleResume(String streamId, String lastEventId, Long userId, HttpServletResponse response) {
        long lastSeq;
        try {
            lastSeq = Long.parseLong(lastEventId.trim());
        } catch (NumberFormatException e) {
            writeErrorResponse(response, 400, "Invalid Last-Event-ID: " + lastEventId);
            return;
        }

        ResumeHandler.ResumeResult result;
        try {
            result = resumeHandler.handleResumeWithAuth(streamId, lastSeq, String.valueOf(userId));
        } catch (ResumeHandler.ResumeException e) {
            writeErrorResponse(response, e.statusCode, e.getMessage());
            return;
        }

        try {
            SseWriter sseWriter = new SseWriter(response);
            response.setHeader("X-Stream-Id", streamId);

            // 只读重放：保留原 seq 作为事件 id，不写入 StreamStore
            for (StreamStore.StreamEvent event : result.events()) {
                sseWriter.send(SseEvent.of(String.valueOf(event.seq()), event.type(), event.data()));
            }

            // 续传以 end 帧收尾
            sseWriter.send(SseEvent.end());
        } catch (IOException e) {
            // 客户端断开或写入失败，静默忽略
        }
    }

    /**
     * 写入 JSON 错误响应
     */
    private void writeErrorResponse(HttpServletResponse response, int status, String message) {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        try {
            response.getWriter().write("{\"error\":\"" + escapeJson(message) + "\"}");
            response.getWriter().flush();
        } catch (IOException e) {
            // 忽略
        }
    }

    private static String escapeJson(String value) {
        if (value == null) return "";
        return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
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
        response.setHeader("X-Conversation-Id", String.valueOf(conversationId));
        eventSink.sendStreamMeta(sseWriter, streamId, String.valueOf(userId));

        // 加载已有上下文（当前 user 消息尚未入库，故不含本条）
        List<Message> historyMsgs;
        try {
            historyMsgs = conversationService.getConversation(userId, conversationId).messages();
        } catch (Exception e) {
            historyMsgs = List.of();
        }

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

        // 5.5 修改行程意图检测：含"第N天" + 修改动词 → 走 Orchestrator.modify 局部重出
        java.util.regex.Matcher dayMatcher = java.util.regex.Pattern.compile("第([一二三四五六七八九十\\d]+)天").matcher(body.message());
        List<Integer> targetDays = new ArrayList<>();
        while (dayMatcher.find()) {
            String tok = dayMatcher.group(1);
            int d = parseChineseDay(tok);
            if (d > 0) targetDays.add(d);
        }
        boolean isModifyIntent = !targetDays.isEmpty()
            && body.message().matches("(?s).*(换成|改成|换一下|调整一下|修改|帮我改|不要|去掉|换成了|改成了|帮我把).*");
        if (isModifyIntent) {
            Map<String, Object> modResult = tripService.modifyLatestTrip(userId, body.message(), targetDays);
            if (Boolean.TRUE.equals(modResult.get("success"))) {
                @SuppressWarnings("unchecked")
                Map<String, Object> data = (Map<String, Object>) modResult.get("data");
                String summary = "已为您修改行程：第" + targetDays + "天已按要求更新，新版本已保存（tripId="
                    + data.get("id") + "）。";
                Map<String, Object> usage = Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0);
                eventSink.sendChunk(sseWriter, streamId, summary);
                eventSink.sendComplete(sseWriter, streamId, usage, List.of("modify_trip"));
                Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
                messagePersistenceService.appendAssistantContent(assistantMsg.getId(), summary);
                messagePersistenceService.forceFlush(assistantMsg.getId(), usage);
                return;
            }
            // 修改失败（如无可用行程）：降级到普通 agent loop
        }

        // 6. Agent 循环：委托 ChatAgent 执行 ReAct 多轮工具循环（LLM 流式 + 工具调用 + Token 记账）
        ChatAgent.ChatResult agentResult = chatAgent.chatStream(
            sseWriter, streamId, userId, body.message(), historyMsgs);
        if (agentResult.budgetExceeded()) {
            return;
        }

        // 7. 发送 complete + 落库
        Map<String, Object> usage = Map.of(
            "prompt", agentResult.promptTokens(),
            "completion", agentResult.completionTokens(),
            "total", agentResult.totalTokens(),
            "cached", 0
        );
        eventSink.sendComplete(sseWriter, streamId, usage, agentResult.executedToolNames());

        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), agentResult.fullText());
        messagePersistenceService.forceFlush(assistantMsg.getId(), usage);
    }

    /**
     * 发送非旅行短路响应
     */
    private void sendShortCircuit(SseWriter sseWriter, String streamId, Long userId, Long userMessageId, Long conversationId) throws IOException {
        // 创建 assistant 空消息
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
        String response = "抱歉，我是旅行规划助手，只能帮助您解决旅游、出行、行程规划相关的问题。请问您有什么旅游出发目的地的计划需要帮助吗？";
        Map<String, Object> usage = Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0);
        eventSink.sendChunk(sseWriter, streamId, response);
        eventSink.sendComplete(sseWriter, streamId, usage);

        // 落库
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), response);
        messagePersistenceService.forceFlush(assistantMsg.getId(), usage);
    }

    /** 把"一".."十"或阿拉伯数字转为天数；无法解析返回 0。 */
    private static int parseChineseDay(String tok) {
        if (tok == null || tok.isEmpty()) return 0;
        try { return Integer.parseInt(tok); } catch (NumberFormatException ignore) {}
        return switch (tok) {
            case "一" -> 1; case "二" -> 2; case "三" -> 3; case "四" -> 4;
            case "五" -> 5; case "六" -> 6; case "七" -> 7; case "八" -> 8;
            case "九" -> 9; case "十" -> 10;
            default -> 0;
        };
    }
}
