package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
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
@Getter
@Setter
public class Message {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long conversationId;

    @Column(nullable = false, length = 50)
    private String role; // user / assistant / system

    @Lob
    @Column(nullable = false)
    private String content;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> metadata;

    @Column(nullable = false)
    private Boolean excludedFromContext = false;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    // 无 updated_at

    protected Message() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }
}
