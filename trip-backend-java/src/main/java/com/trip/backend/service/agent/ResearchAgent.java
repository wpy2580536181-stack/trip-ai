package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import com.trip.backend.service.agent.tools.RetrieveKnowledgeTool;
import com.trip.backend.service.agent.tools.CalculateDistanceTool;
import com.trip.backend.service.agent.tools.SearchHotelsTool;
import com.trip.backend.service.agent.tools.CommuteTools;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * ResearchAgent 研究代理
 *
 * 职责：
 * - 并行调用 5 个工具（attractions/food/hotels/weather/distance）
 * - 汇总 ResearchBundle
 * - 发送 tool_start/tool_end 事件
 */
@Service
public class ResearchAgent {

    private static final Logger log = LoggerFactory.getLogger(ResearchAgent.class);

    private final RetrieveKnowledgeTool retrieveKnowledgeTool;
    private final SearchHotelsTool searchHotelsTool;
    private final CalculateDistanceTool calculateDistanceTool;
    private final CommuteTools commuteTools;

    // 并行执行线程池
    private final ExecutorService executor = Executors.newFixedThreadPool(5);

    public ResearchAgent(
            RetrieveKnowledgeTool retrieveKnowledgeTool,
            SearchHotelsTool searchHotelsTool,
            CalculateDistanceTool calculateDistanceTool,
            CommuteTools commuteTools) {
        this.retrieveKnowledgeTool = retrieveKnowledgeTool;
        this.searchHotelsTool = searchHotelsTool;
        this.calculateDistanceTool = calculateDistanceTool;
        this.commuteTools = commuteTools;
    }

    /**
     * 执行研究（并行调用 5 个工具）
     *
     * @param input 研究输入
     * @return 研究结果包
     */
    public CompletableFuture<ResearchBundle> research(ResearchInput input) {
        log.info("[ResearchAgent] Starting research: city={}, days={}, budget={}",
            input.city(), input.days(), input.budget());

        // 并行调用 5 个工具
        CompletableFuture<List<Map<String, Object>>> attractionsFuture = CompletableFuture.supplyAsync(
            () -> callToolWithEvent("attractions", () -> retrieveKnowledgeTool.execute(
                input.city() + " 景点", input.city(), "景点")), executor);

        CompletableFuture<List<Map<String, Object>>> foodFuture = CompletableFuture.supplyAsync(
            () -> callToolWithEvent("food", () -> retrieveKnowledgeTool.execute(
                input.city() + " 美食", input.city(), "美食")), executor);

        CompletableFuture<List<Map<String, Object>>> hotelsFuture = CompletableFuture.supplyAsync(
            () -> callToolWithEvent("hotels", () -> searchHotelsTool.execute(
                input.city(), input.budget() != null ? input.budget() / (input.days() * 2) : null, null)), executor);

        CompletableFuture<Map<String, Object>> weatherFuture = CompletableFuture.supplyAsync(
            () -> callToolWithEvent("weather", () -> Map.of("status", "unavailable")), executor);

        CompletableFuture<Map<String, Object>> distanceFuture = CompletableFuture.supplyAsync(
            () -> callToolWithEvent("distance", () -> {
                if (input.departureCity() != null) {
                    String result = calculateDistanceTool.execute(input.departureCity(), input.city(), "car");
                    return Map.of("result", result);
                }
                return Map.of("status", "no_departure_city");
            }), executor);

        // 等待全部完成
        return CompletableFuture.allOf(attractionsFuture, foodFuture, hotelsFuture, weatherFuture, distanceFuture)
            .thenApply(v -> new ResearchBundle(
                attractionsFuture.join(),
                foodFuture.join(),
                hotelsFuture.join(),
                weatherFuture.join(),
                distanceFuture.join()
            ))
            .whenComplete((result, error) -> {
                if (error != null) {
                    log.error("[ResearchAgent] Research failed", error);
                } else {
                    log.info("[ResearchAgent] Research completed");
                }
            });
    }

    /**
     * 调用工具并发送事件
     */
    private <T> T callToolWithEvent(String key, java.util.function.Supplier<T> supplier) {
        log.debug("[ResearchAgent] tool_start: {}", key);
        try {
            T result = supplier.get();
            log.debug("[ResearchAgent] tool_end: {}", key);
            return result;
        } catch (Exception e) {
            log.warn("[ResearchAgent] tool_error: {}", key, e);
            throw e;
        }
    }
}
