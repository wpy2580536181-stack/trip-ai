package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

/**
 * 会话实体（对应 Python models/conversation.py）
 * - 有 updated_at
 */
@Entity
@Table(name = "conversations", indexes = {
    @Index(name = "idx_conversations_user_id", columnList = "user_id"),
    @Index(name = "idx_conversations_updated_at", columnList = "updated_at")
})
public class Conversation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long userId;

    @Column(length = 200)
    private String title;

    @Column(columnDefinition = "text")
    private String summary;

    @Column(columnDefinition = "text")
    private String recap;

    @Column(columnDefinition = "text")
    private String summaryError;

    @Column
    private OffsetDateTime summaryAt;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    @Column(nullable = false)
    private OffsetDateTime updatedAt;

    public Conversation() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
        this.updatedAt = OffsetDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = OffsetDateTime.now();
    }

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public Long getUserId() {
        return userId;
    }

    public String getTitle() {
        return title;
    }

    public String getSummary() {
        return summary;
    }

    public String getRecap() {
        return recap;
    }

    public String getSummaryError() {
        return summaryError;
    }

    public OffsetDateTime getSummaryAt() {
        return summaryAt;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public OffsetDateTime getUpdatedAt() {
        return updatedAt;
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public void setSummary(String summary) {
        this.summary = summary;
    }

    public void setRecap(String recap) {
        this.recap = recap;
    }

    public void setSummaryError(String summaryError) {
        this.summaryError = summaryError;
    }

    public void setSummaryAt(OffsetDateTime summaryAt) {
        this.summaryAt = summaryAt;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public void setUpdatedAt(OffsetDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
