package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * Research 输入 DTO
 */
public record ResearchInput(
    String city,
    Integer days,
    Integer budget,
    String departureCity,
    List<String> interests
) {}
