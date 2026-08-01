package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;

/**
 * Agent 步骤实体（对应 Python models/agent_step.py）
 * - args 为 JSONB 列
 * - 无 updated_at
 * - ondelete CASCADE（message_id FK）
 */
@Entity
@Table(name = "agent_steps", indexes = {
    @Index(name = "idx_agent_steps_message_id", columnList = "message_id, step")
})
@Getter
@Setter
public class AgentStep {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long messageId;

    @Column(nullable = false)
    private Integer step;

    @Column(nullable = false, length = 100)
    private String type;

    @Column(nullable = false, length = 200)
    private String name;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> args;

    @Lob
    private String output;

    @Column
    private Long durationMs;

    @Column(length = 500)
    private String error;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    // 无 updated_at

    protected AgentStep() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }
}
