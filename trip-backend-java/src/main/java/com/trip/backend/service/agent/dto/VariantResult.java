package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * 行程变体 DTO
 */
public record VariantResult(
    String name,
    Map<String, Object> plan,
    String rationale
) {}
