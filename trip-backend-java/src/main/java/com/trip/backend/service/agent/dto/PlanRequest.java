package com.trip.backend.service.agent.dto;

/**
 * 计划请求（G4 简化版）
 */
public record PlanRequest(
    String city,
    Integer days,
    Integer budget
) {}
