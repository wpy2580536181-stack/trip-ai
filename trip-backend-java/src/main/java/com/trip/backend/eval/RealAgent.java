package com.trip.backend.eval;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * RealAgent：调用真实 Java 后端 API（简化版）
 */
public class RealAgent {

    private final String baseUrl;
    private final HttpClient httpClient;

    public RealAgent(String baseUrl) {
        this.baseUrl = baseUrl;
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();
    }

    /**
     * 调用真实 Agent
     */
    public Map<String, Object> call(String message) {
        try {
            // 简化实现：直接返回占位符
            Map<String, Object> tokens = Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0);
            Map<String, Object> result = new java.util.LinkedHashMap<>();
            result.put("text", "RealAgent 占位符: " + message);
            result.put("error", "");
            result.put("tokens", tokens);
            result.put("durationMs", 0);
            return result;
        } catch (Exception e) {
            Map<String, Object> tokens = Map.of("prompt", 0, "completion", 0, "total", 0, "cached", 0);
            Map<String, Object> result = new java.util.LinkedHashMap<>();
            result.put("text", "");
            result.put("error", e.getMessage() != null ? e.getMessage() : "");
            result.put("tokens", tokens);
            result.put("durationMs", 0);
            return result;
        }
    }
}
