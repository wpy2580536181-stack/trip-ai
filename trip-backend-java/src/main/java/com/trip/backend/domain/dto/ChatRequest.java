package com.trip.backend.domain.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * 对话请求 DTO（对应 Python schemas/trip.py::ChatRequest）
 *
 * 字段别名映射：
 * - conversationId → conversation_id
 * - tripId → trip_id
 */
public record ChatRequest(
    @NotBlank(message = "消息不能为空") String message,

    Long conversationId,  // alias conversation_id

    Long tripId           // alias trip_id
) {}
