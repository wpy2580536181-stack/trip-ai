package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

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
@Getter
@Setter
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

    protected Conversation() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
        this.updatedAt = OffsetDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        this.updatedAt = OffsetDateTime.now();
    }
}
