package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.List;

/**
 * 反馈实体（对应 Python models/feedback.py）
 * - tags 为 JSONB 列
 * - 唯一约束 (user_id, message_id)
 * - ondelete CASCADE（message_id FK）
 */
@Entity
@Table(name = "feedbacks", indexes = {
    @Index(name = "idx_feedbacks_message_id", columnList = "message_id"),
    @Index(name = "idx_feedbacks_rating_created", columnList = "rating, created_at"),
    @Index(name = "idx_feedbacks_user_created", columnList = "user_id, created_at")
})
public class Feedback {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name="user_id", nullable = false)
    private Long userId;

    @Column(name="message_id", nullable = false)
    private Long messageId;

    @Column(name="conversation_id", nullable = false)
    private Long conversationId;

    @Column(nullable = false)
    private Integer rating; // 1 或 -1

    @Column(length = 500)
    private String comment;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "json")
    private List<String> tags;

    @Column(name="created_at", nullable = false)
    private OffsetDateTime createdAt;

    protected Feedback() {}

    // ==================== Public Constructor (供 Service 层使用) ====================

    public Feedback(Long userId, Long messageId, Integer rating) {
        this.userId = userId;
        this.messageId = messageId;
        this.rating = rating;
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

    public Long getMessageId() {
        return messageId;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public Integer getRating() {
        return rating;
    }

    public String getComment() {
        return comment;
    }

    public List<String> getTags() {
        return tags;
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

    public void setMessageId(Long messageId) {
        this.messageId = messageId;
    }

    public void setConversationId(Long conversationId) {
        this.conversationId = conversationId;
    }

    public void setRating(Integer rating) {
        this.rating = rating;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
