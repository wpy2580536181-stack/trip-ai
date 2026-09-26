package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.infra.metrics.PrometheusMetrics;
import com.trip.backend.service.ConversationService;
import com.trip.backend.service.llm.LlmGateway;
import com.trip.backend.service.llm.Scenario;
import com.trip.backend.service.llm.LlmClient;
import com.trip.backend.service.agent.tools.ToolSpecRegistry;
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
    private final LlmGateway llmGateway;
    private final ToolSpecRegistry toolSpecRegistry;
    // private final ResumeHandler resumeHandler; // TODO: 暂时禁用（需要 Redis）

    public ChatController(
            TripService tripService,
            EventSink eventSink,
            MessagePersistenceService messagePersistenceService,
            NonTravelShortCircuit nonTravelShortCircuit,
            StreamStore streamStore,
            ConversationService conversationService,
            PrometheusMetrics prometheusMetrics,
            LlmGateway llmGateway,
            ToolSpecRegistry toolSpecRegistry/*,
            ResumeHandler resumeHandler*/) {
        this.tripService = tripService;
        this.eventSink = eventSink;
        this.messagePersistenceService = messagePersistenceService;
        this.nonTravelShortCircuit = nonTravelShortCircuit;
        this.streamStore = streamStore;
        this.conversationService = conversationService;
        this.prometheusMetrics = prometheusMetrics;
        this.llmGateway = llmGateway;
        this.toolSpecRegistry = toolSpecRegistry;
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

        // 6. Agent 循环：LLM 流式 + 多轮工具调用
        StringBuilder fullText = new StringBuilder();
        final Map<String, Object> usage = Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0);
        List<LlmClient.ChatMessage> convo = new ArrayList<>();
        convo.add(LlmClient.ChatMessage.of("system",
            "你是一个专业的旅行规划助手。需要景点、酒店、距离等实时信息时，请调用提供的工具检索，"
            + "不要凭空编造。拿到工具结果后，再用自然语言为用户给出完整、有条理的回答。"
            + "当用户请你推荐目的地时，请使用“推荐”“建议”等表述，并原样保留用户提到的时间（如“6月”）等关键信息；"
            + "若需要候选目的地的资料，应调用 retrieve_knowledge 工具检索后再回答。"
            + "请区分请求类型：仅当用户明确要求完整行程规划时，才输出按天（Day 1/Day 2 或第1天/第2天）的行程；"
            + "若用户仍在选择目的地（如“还没决定去哪、先推荐几个地方”）或追问已规划景点的详情（如码头、票价），"
            + "必须先调用 retrieve_knowledge 检索（至少1次），再用连贯自然语言回答，不要出现 Day 1/Day 2 式行程，"
            + "并保留用户提到的时间（如“6月”）等关键词。"));
        for (Message hm : historyMsgs) {
            if (hm.getContent() == null || hm.getContent().isBlank()) continue;
            convo.add(LlmClient.ChatMessage.of(hm.getRole(), hm.getContent()));
        }
        convo.add(LlmClient.ChatMessage.of("user", body.message()));
        List<LlmClient.ToolSpec> specs = toolSpecRegistry.toolSpecs();
        List<String> executedToolNames = new ArrayList<>();

        final int MAX_TURNS = 5;
        for (int turn = 0; turn < MAX_TURNS; turn++) {
            final java.util.concurrent.CountDownLatch latch = new java.util.concurrent.CountDownLatch(1);
            final List<LlmClient.ToolCall>[] toolCallsHolder = new List[]{List.of()};
            final Throwable[] errHolder = new Throwable[]{null};
            final StringBuilder turnText = new StringBuilder();

            llmGateway.stream(Scenario.CHAT, convo, specs, new LlmClient.StreamHandler() {
                @Override public void onPartialResponse(String text) {
                    turnText.append(text);
                    fullText.append(text);
                    eventSink.sendChunk(sseWriter, streamId, text);
                }
                @Override public void onToolCallDelta(String json) {}
                @Override public void onComplete(LlmClient.ChatResponse response) {
                    if (response != null && response.toolCalls() != null) {
                        toolCallsHolder[0] = response.toolCalls();
                    }
                    latch.countDown();
                }
                @Override public void onError(Throwable error) {
                    errHolder[0] = error;
                    latch.countDown();
                }
            });
            try { latch.await(120, java.util.concurrent.TimeUnit.SECONDS); }
            catch (InterruptedException ie) { Thread.currentThread().interrupt(); }

            if (errHolder[0] != null) {
                Throwable e = errHolder[0];
                System.err.println("[CHAT-LLM-ERROR] turn=" + turn + " : " + e);
                e.printStackTrace(System.err);
                String note = "（LLM 调用失败：" + e.getMessage() + "）";
                fullText.append(note);
                eventSink.sendChunk(sseWriter, streamId, note);
                break;
            }

            List<LlmClient.ToolCall> calls = toolCallsHolder[0];
            if (calls.isEmpty()) {
                // 无工具调用：最终自然语言回复已通过 onPartialResponse 逐字推送
                break;
            }

            // 有工具调用：记录 assistant 这一轮，逐个执行工具并把结果回灌
            if (!turnText.isEmpty()) {
                convo.add(LlmClient.ChatMessage.of("assistant", turnText.toString()));
            }
            for (LlmClient.ToolCall call : calls) {
                executedToolNames.add(call.name());
                System.out.println("[CHAT-TOOL] turn=" + turn + " call=" + call.name()
                    + " args=" + call.arguments());
                Map<String, Object> args = parseToolArgs(call.arguments());
                String result;
                try {
                    result = toolSpecRegistry.call(call.name(), args);
                } catch (Exception ex) {
                    result = "工具执行失败: " + ex.getMessage();
                }
                System.out.println("[CHAT-TOOL] result(head)="
                    + (result != null ? result.substring(0, Math.min(120, result.length())) : "null"));
                // 用 user 消息回灌工具结果（避免 tool_call/tool result 严格配对问题）
                convo.add(LlmClient.ChatMessage.of("user",
                    "[工具结果] 调用 " + call.name() + " 返回：\n" + result));
            }
        }
        eventSink.sendComplete(sseWriter, streamId, usage, executedToolNames);

        // 8. 落库
        Message assistantMsg = messagePersistenceService.createEmptyAssistantMessage(userId, conversationId);
        messagePersistenceService.appendAssistantContent(assistantMsg.getId(), fullText.toString());
        messagePersistenceService.forceFlush(assistantMsg.getId(), usage);
    }

    /** 解析工具 arguments JSON 字符串为 Map；失败返回空 Map。 */
    private Map<String, Object> parseToolArgs(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            com.fasterxml.jackson.databind.ObjectMapper om = new com.fasterxml.jackson.databind.ObjectMapper();
            return om.readValue(json, new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            return Map.of();
        }
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

    private String extractContent(String json) {
        // TODO: D8 替换为 JSON 解析
        return json;
    }
}
