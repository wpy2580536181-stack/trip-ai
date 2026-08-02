package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import com.trip.backend.service.chat.EventSink;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * ChatAgent 聊天代理
 *
 * 对应 Python services/agent/agents/chat_agent.py
 *
 * 功能：
 * - 预检测（通勤/附近关键词）
 * - 单次流式（bind_tools + tool_calls 分派）
 * - 四工具分派（trigger_plan/modify/patch/select_skill）
 * - 卡片事件（info_text/poi_list/commute_compare）
 * - 降级处理
 */
@Service
public class ChatAgent {

    private static final Logger log = LoggerFactory.getLogger(ChatAgent.class);

    private final LlmClient llmClient;
    private final ToolSpecRegistry toolRegistry;
    private final EventSink eventSink;

    public ChatAgent(LlmClient llmClient, ToolSpecRegistry toolRegistry, EventSink eventSink) {
        this.llmClient = llmClient;
        this.toolRegistry = toolRegistry;
        this.eventSink = eventSink;
    }

    /**
     * 处理用户消息（单次流式）
     *
     * @param userId 用户 ID
     * @param message 用户消息
     * @param conversationId 会话 ID
     * @param tripId 行程 ID（可选）
     * @return 响应
     */
    public CompletableFuture<ChatResponse> chat(Long userId, String message, Long conversationId, Long tripId) {
        log.info("[ChatAgent] Processing message: userId={}, message={}", userId, message);

        return CompletableFuture.supplyAsync(() -> {
            try {
                // 1. 预检测（通勤/附近关键词）
                if (isCommuteIntent(message)) {
                    return handleCommuteIntent(message);
                }

                // 2. 流式 LLM 调用
                StringBuilder contentBuffer = new StringBuilder();
                List<ToolCall> toolCalls = new java.util.ArrayList<>();

                llmClient.stream(
                    List.of(new ChatMessage("user", message)),
                    List.of(), // TODO: D8 绑定工具
                    new LlmClient.StreamHandler() {
                        @Override
                        public void onPartialResponse(String content) {
                            contentBuffer.append(content);
                            // 发送 chunk 事件
                            eventSink.sendChunk(conversationId.toString(), content);
                        }

                        @Override
                        public void onToolCall(ToolCall toolCall) {
                            toolCalls.add(toolCall);
                        }

                        @Override
                        public void onComplete(ChatResponse response) {
                            // 流完成
                        }

                        @Override
                        public void onError(Throwable error) {
                            log.error("[ChatAgent] Stream error", error);
                        }
                    }
                ).join();

                // 3. 流后分派（四工具分支）
                if (!toolCalls.isEmpty()) {
                    return dispatchTools(userId, message, toolCalls, conversationId, tripId);
                }

                // 4. 普通回复
                String content = contentBuffer.toString();
                return new ChatResponse(content, List.of(), TokenUsage.empty());

            } catch (Exception e) {
                log.error("[ChatAgent] Chat failed", e);
                return new ChatResponse("抱歉，处理您的消息时出错了。", List.of(), TokenUsage.empty());
            }
        });
    }

    /**
     * 判断是否为通勤意图
     */
    private boolean isCommuteIntent(String message) {
        // TODO: D8 实现后补充
        return false;
    }

    /**
     * 处理通勤意图
     */
    private ChatResponse handleCommuteIntent(String message) {
        // TODO: D8 实现后补充
        return new ChatResponse("通勤功能开发中...", List.of(), TokenUsage.empty());
    }

    /**
     * 流后分派（四工具分支）
     */
    private ChatResponse dispatchTools(Long userId, String message, List<ToolCall> toolCalls,
                                       Long conversationId, Long tripId) {
        // TODO: D8 实现后补充
        return new ChatResponse("工具调用开发中...", List.of(), TokenUsage.empty());
    }
}
