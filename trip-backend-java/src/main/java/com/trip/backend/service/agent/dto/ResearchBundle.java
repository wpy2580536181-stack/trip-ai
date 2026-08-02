package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * Research Bundle DTO
 */
public record ResearchBundle(
    List<Map<String, Object>> attractions,
    List<Map<String, Object>> food,
    List<Map<String, Object>> hotels,
    Map<String, Object> weather,
    Map<String, Object> distance
) {}
