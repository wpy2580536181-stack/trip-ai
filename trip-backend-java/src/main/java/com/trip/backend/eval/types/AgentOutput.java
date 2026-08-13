package com.trip.backend.eval.types;

/**
 * AgentOutput: Agent 输出
 */
public class AgentOutput {
    public String text = "";
    public String error;
    public long durationMs = 0;
    public Long conversationId = null;
}
