package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.OffsetDateTime;

/**
 * Token 使用日志实体（对应 Python models/token_usage_log.py）
 * - conversation_id / message_id 为 SET NULL
 * - 无 updated_at
 */
@Entity
@Table(name = "token_usage_logs", indexes = {
    @Index(name = "idx_token_usage_user_created", columnList = "user_id, created_at"),
    @Index(name = "idx_token_usage_request_type", columnList = "request_type")
})
@Getter
@Setter
public class TokenUsageLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long userId;

    @Column(nullable = false, length = 50)
    private String requestType; // chat / recommend / skill / etc.

    @Column(length = 100)
    private String route;

    // SET NULL on delete
    @Column
    private Long conversationId;

    // SET NULL on delete
    @Column
    private Long messageId;

    @Column(nullable = false)
    private Integer promptTokens;

    @Column(nullable = false)
    private Integer completionTokens;

    @Column(nullable = false)
    private Integer totalTokens;

    @Column
    private Integer cachedTokens;

    @Column
    private Integer latencyMs; // LLM 请求耗时

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    // 无 updated_at

    protected TokenUsageLog() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }
}
