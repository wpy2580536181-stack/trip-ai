package com.trip.backend.domain.entity;

import jakarta.persistence.*;
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
    @Column(columnDefinition = "json")
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

    public AgentStep() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public Long getMessageId() {
        return messageId;
    }

    public Long getConversationId() {
        // TODO: 添加 conversation_id 字段
        return null;
    }

    public Integer getStep() {
        return step;
    }

    public String getStepName() {
        return name; // 兼容：使用 name 字段
    }

    public String getStepType() {
        return type;
    }

    public String getStatus() {
        // TODO: 添加 status 字段
        return "completed";
    }

    public String getType() {
        return type;
    }

    public String getName() {
        return name;
    }

    public Map<String, Object> getArgs() {
        return args;
    }

    public String getOutput() {
        return output;
    }

    public Long getDurationMs() {
        return durationMs;
    }

    public String getError() {
        return error;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setMessageId(Long messageId) {
        this.messageId = messageId;
    }

    public void setConversationId(Long conversationId) {
        // TODO: 添加 conversation_id 字段
    }

    public void setStep(Integer step) {
        this.step = step;
    }

    public void setStepName(String stepName) {
        this.name = stepName; // 兼容：映射到 name 字段
    }

    public void setStepType(String stepType) {
        this.type = stepType;
    }

    public void setStatus(String status) {
        // TODO: 添加 status 字段
    }

    public void setType(String type) {
        this.type = type;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setArgs(Map<String, Object> args) {
        this.args = args;
    }

    public void setOutput(String output) {
        this.output = output;
    }

    public void setDurationMs(Long durationMs) {
        this.durationMs = durationMs;
    }

    public void setError(String error) {
        this.error = error;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
