package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * Token 用量 DTO
 */
public record TokenUsage(
    int prompt,
    int completion,
    int total,
    int cached
) {
    public TokenUsage {
        if (prompt < 0 || completion < 0 || total < 0 || cached < 0) {
            throw new IllegalArgumentException("Token usage fields must be non-negative");
        }
    }

    public static TokenUsage empty() {
        return new TokenUsage(0, 0, 0, 0);
    }

    public TokenUsage merge(TokenUsage other) {
        return new TokenUsage(
            this.prompt + other.prompt,
            this.completion + other.completion,
            this.total + other.total,
            this.cached + other.cached
        );
    }
}
