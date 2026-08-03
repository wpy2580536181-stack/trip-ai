package com.trip.backend.service.agent.dto;

/**
 * 计划请求（简化版）
 */
public record PlanRequest(
    String city,
    Integer days,
    Integer budget
) {}
