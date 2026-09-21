package com.trip.backend.service.llm;

import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.output.TokenUsage;
import dev.langchain4j.data.message.*;

import java.util.List;

/**
 * LLM 客户端接口
 * 抽象 langchain4j 实现，便于后续替换
 */
public interface LlmClient {

    /**
     * 非流式调用
     */
    ChatResponse invoke(List<ChatMessage> messages);

    /**
     * 非流式调用（带工具）
     */
    ChatResponse invoke(List<ChatMessage> messages, List<ToolSpec> tools);

    /**
     * 流式调用
     */
    void stream(List<ChatMessage> messages, StreamHandler handler);

    /**
     * 流式调用（带工具）
     */
    void stream(List<ChatMessage> messages, List<ToolSpec> tools, StreamHandler handler);

    /**
     * 检查是否可用
     */
    boolean isAvailable();

    /**
     * 响应类
     */
    record ChatResponse(
        String content,
        List<ToolCall> toolCalls,
        TokenUsage tokenUsage
    ) {}

    /**
     * 工具调用
     */
    record ToolCall(
        String name,
        String arguments
    ) {}

    /**
     * 工具规格
     */
    record ToolSpec(
        String name,
        String description,
        String parametersSchema
    ) {}

    /**
     * 聊天消息
     *
     * role=tool 时需通过 {@link #toolResult} 构造，携带 toolCallId/toolName，
     * 以便 Langchain4j 侧转成 ToolExecutionResultMessage。
     */
    record ChatMessage(
        String role,
        String content,
        String toolCallId,
        String toolName
    ) {
        /** 普通消息（system/user/assistant） */
        public static ChatMessage of(String role, String content) {
            return new ChatMessage(role, content, null, null);
        }

        /** tool 执行结果消息（对应 assistant 的一次 tool_call） */
        public static ChatMessage toolResult(String toolCallId, String toolName, String content) {
            return new ChatMessage("tool", content, toolCallId, toolName);
        }
    }

    /**
     * 流式处理器
     */
    interface StreamHandler {
        void onPartialResponse(String text);
        void onToolCallDelta(String toolCallJson);
        void onComplete(ChatResponse response);
        void onError(Throwable error);
    }
}
