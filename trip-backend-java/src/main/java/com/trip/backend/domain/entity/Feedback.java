package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
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
@Getter
@Setter
public class Feedback {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long userId;

    @Column(nullable = false)
    private Long messageId;

    @Column(nullable = false)
    private Long conversationId;

    @Column(nullable = false)
    private Integer rating; // 1 或 -1

    @Column(length = 500)
    private String comment;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<String> tags;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    protected Feedback() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }
}
