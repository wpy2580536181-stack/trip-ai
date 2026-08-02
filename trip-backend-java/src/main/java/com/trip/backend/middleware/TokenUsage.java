package com.trip.backend.middleware;

import java.time.Instant;

/**
 * Token 使用记录
 */
public class TokenUsage {

    private final long userId;
    private final String requestType;
    private final String route;
    private final int promptTokens;
    private final int completionTokens;
    private final int totalTokens;
    private final Integer cachedTokens;
    private final Integer latencyMs;

    public TokenUsage(long userId, String requestType, String route,
                     int promptTokens, int completionTokens, int totalTokens,
                     Integer cachedTokens, Integer latencyMs) {
        this.userId = userId;
        this.requestType = requestType;
        this.route = route;
        this.promptTokens = promptTokens;
        this.completionTokens = completionTokens;
        this.totalTokens = totalTokens;
        this.cachedTokens = cachedTokens;
        this.latencyMs = latencyMs;
    }

    // Getters
    public long getUserId() { return userId; }
    public String getRequestType() { return requestType; }
    public String getRoute() { return route; }
    public int getPromptTokens() { return promptTokens; }
    public int getCompletionTokens() { return completionTokens; }
    public int getTotalTokens() { return totalTokens; }
    public Integer getCachedTokens() { return cachedTokens; }
    public Integer getLatencyMs() { return latencyMs; }
}
