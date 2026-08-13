package com.trip.backend.eval;

import java.util.Map;

/**
 * RealAgent：调用真实 Java 后端 API（骨架）
 */
public class RealAgent {

    private final String baseUrl;

    public RealAgent(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    /**
     * 调用真实 Agent
     */
    public Map<String, Object> call(String message) {
        // TODO: 实现真实 API 调用
        return Map.of(
            "text", "RealAgent 占位符: " + message,
            "error", null
        );
    }
}
