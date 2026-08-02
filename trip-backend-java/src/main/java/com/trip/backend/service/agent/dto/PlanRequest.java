package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * 计划请求 DTO
 */
public record PlanRequest(
    String city,
    Integer days,
    Integer budget,
    String departureCity,
    List<String> interests,
    Long userId
) {}
