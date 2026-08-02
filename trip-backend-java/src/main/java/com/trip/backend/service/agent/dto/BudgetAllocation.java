package com.trip.backend.service.agent.dto;

import java.util.List;
import java.util.Map;

/**
 * 预算分配 DTO
 */
public record BudgetAllocation(
    int totalBudget,
    int hotelBudget,
    int foodBudget,
    int transportBudget,
    int ticketBudget,
    int otherBudget,
    Map<String, Object> targetSplit
) {
    public static BudgetAllocation of(int totalBudget) {
        int hotel = (int) (totalBudget * 0.25);
        int food = (int) (totalBudget * 0.20);
        int transport = (int) (totalBudget * 0.15);
        int ticket = (int) (totalBudget * 0.30);
        int other = totalBudget - hotel - food - transport - ticket;

        return new BudgetAllocation(
            totalBudget,
            hotel,
            food,
            transport,
            ticket,
            other,
            Map.of(
                "hotel", hotel,
                "food", food,
                "transport", transport,
                "ticket", ticket,
                "other", other
            )
        );
    }
}
