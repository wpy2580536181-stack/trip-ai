package com.trip.backend.eval.types;

import java.util.List;

/**
 * Agent 完整输出
 */
public class AgentOutput {
    private String text = "";
    private Object json;
    private List<ToolCall> toolCalls;
    private String error;
    private TokenUsage tokens;
    private long durationMs = 0;
    private Long conversationId;

    public AgentOutput() {
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }

    public Object getJson() {
        return json;
    }

    public void setJson(Object json) {
        this.json = json;
    }

    public List<ToolCall> getToolCalls() {
        return toolCalls;
    }

    public void setToolCalls(List<ToolCall> toolCalls) {
        this.toolCalls = toolCalls;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }

    public TokenUsage getTokens() {
        return tokens;
    }

    public void setTokens(TokenUsage tokens) {
        this.tokens = tokens;
    }

    public long getDurationMs() {
        return durationMs;
    }

    public void setDurationMs(long durationMs) {
        this.durationMs = durationMs;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public void setConversationId(Long conversationId) {
        this.conversationId = conversationId;
    }
}
