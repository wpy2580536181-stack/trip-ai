package com.trip.backend.domain.entity;

import jakarta.persistence.*;
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

    public TokenUsageLog(Long userId, String requestType, String route,
                         Integer promptTokens, Integer completionTokens,
                         Integer totalTokens, Integer cachedTokens,
                         Integer latencyMs) {
        this.userId = userId;
        this.requestType = requestType;
        this.route = route;
        this.promptTokens = promptTokens;
        this.completionTokens = completionTokens;
        this.totalTokens = totalTokens;
        this.cachedTokens = cachedTokens;
        this.latencyMs = latencyMs;
    }

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public Long getUserId() {
        return userId;
    }

    public String getRequestType() {
        return requestType;
    }

    public String getRoute() {
        return route;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public Long getMessageId() {
        return messageId;
    }

    public Integer getPromptTokens() {
        return promptTokens;
    }

    public Integer getCompletionTokens() {
        return completionTokens;
    }

    public Integer getTotalTokens() {
        return totalTokens;
    }

    public Integer getCachedTokens() {
        return cachedTokens;
    }

    public Integer getLatencyMs() {
        return latencyMs;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public void setRequestType(String requestType) {
        this.requestType = requestType;
    }

    public void setRoute(String route) {
        this.route = route;
    }

    public void setConversationId(Long conversationId) {
        this.conversationId = conversationId;
    }

    public void setMessageId(Long messageId) {
        this.messageId = messageId;
    }

    public void setPromptTokens(Integer promptTokens) {
        this.promptTokens = promptTokens;
    }

    public void setCompletionTokens(Integer completionTokens) {
        this.completionTokens = completionTokens;
    }

    public void setTotalTokens(Integer totalTokens) {
        this.totalTokens = totalTokens;
    }

    public void setCachedTokens(Integer cachedTokens) {
        this.cachedTokens = cachedTokens;
    }

    public void setLatencyMs(Integer latencyMs) {
        this.latencyMs = latencyMs;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
