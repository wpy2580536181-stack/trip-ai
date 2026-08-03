package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;

/**
 * 消息实体（对应 Python models/message.py）
 * - metadata 为 JSONB 列
 * - 无 updated_at
 * - ondelete CASCADE（conversation_id FK）
 */
@Entity
@Table(name = "messages", indexes = {
    @Index(name = "idx_messages_conv_created", columnList = "conversation_id, created_at"),
    @Index(name = "idx_messages_excluded", columnList = "conversation_id, excluded_from_context")
})
public class Message {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "conversation_id", nullable = false)
    private Long conversationId;

    @Column(nullable = false, length = 50)
    private String role; // user / assistant / system

    @Lob
    @Column(nullable = false)
    private String content;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "json")
    private Map<String, Object> metadata;

    @Column(name = "excluded_from_context", nullable = false)
    private Boolean excludedFromContext = false;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    // 无 updated_at

    public Message() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public String getRole() {
        return role;
    }

    public String getContent() {
        return content;
    }

    public Map<String, Object> getMetadata() {
        return metadata;
    }

    public Boolean getExcludedFromContext() {
        return excludedFromContext;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setConversationId(Long conversationId) {
        this.conversationId = conversationId;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public void setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
    }

    public void setExcludedFromContext(Boolean excludedFromContext) {
        this.excludedFromContext = excludedFromContext;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
