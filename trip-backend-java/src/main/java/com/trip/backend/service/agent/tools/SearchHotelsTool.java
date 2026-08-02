package com.trip.backend.service.agent.tools;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.service.KnowledgeService;
import com.trip.backend.infra.resilience.CircuitBreaker;
import com.trip.backend.infra.resilience.ToolResilienceWrapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;

/**
 * Search Hotels 工具
 *
 * 对应 Python tools/search_hotels.py
 *
 * 功能：
 * - 查询目标城市的住宿信息
 * - 支持 budget/level 过滤
 * - 韧性包装（超时 10s + 重试 1 + 熔断 5/30s + fallback）
 */
public class SearchHotelsTool {

    private static final Logger log = LoggerFactory.getLogger(SearchHotelsTool.class);

    private final KnowledgeService knowledgeService;
    private final ToolResilienceWrapper resilienceWrapper;
    private final CircuitBreaker circuitBreaker;

    public SearchHotelsTool(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
        this.circuitBreaker = CircuitBreaker.getOrCreate("search_hotels", 5, 30_000);
        this.resilienceWrapper = ToolResilienceWrapper.builder()
            .timeout(10_000)
            .retries(1)
            .fallback("住宿信息暂时不可用，请基于通用旅行知识回答。")
            .circuitBreaker(circuitBreaker)
            .build();
    }

    /**
     * 执行工具调用
     *
     * @param city 目标城市
     * @param budget 预算上限（可选）
     * @param level 住宿档次（可选：economy/comfort/luxury）
     * @return 住宿信息字符串
     */
    public String execute(String city, Double budget, String level) {
        return execute(city, budget, level, 5);
    }

    /**
     * 执行工具调用（内部方法）
     */
    String execute(String city, Double budget, String level, int limit) {
        try {
            // 构建搜索查询
            StringBuilder query = new StringBuilder();
            if (level != null && !level.isBlank()) {
                query.append(level).append(" ");
            }
            query.append(city).append(" 住宿酒店");

            // 调用检索
            List<Spot> results = resilienceWrapper.execute(() ->
                knowledgeService.searchSpots(query.toString(), city, "hotel", limit)
            );

            if (results == null || results.isEmpty()) {
                String budgetStr = budget != null ? String.format("，预算 %.0f 元/晚", budget) : "";
                return String.format("知识库中暂无 %s 的住宿数据%s。请基于通用知识推荐。", city, budgetStr);
            }

            // 格式化结果
            StringBuilder sb = new StringBuilder();
            sb.append(String.format("在 %s 找到 %d 个住宿推荐：\n\n", city, results.size()));

            for (int i = 0; i < Math.min(results.size(), limit); i++) {
                Spot spot = results.get(i);
                sb.append(String.format("%d. **%s**\n", i + 1, spot.getName()));
                if (spot.getDescription() != null && !spot.getDescription().isBlank()) {
                    sb.append(String.format("   %s\n", spot.getDescription()));
                }
                if (spot.getRating() != null) {
                    sb.append(String.format("   评分：%.1f\n", spot.getRating()));
                }
                if (spot.getAvgCost() != null) {
                    sb.append(String.format("   价格：%s\n", spot.getAvgCost()));
                }
                if (spot.getAddress() != null && !spot.getAddress().isBlank()) {
                    sb.append(String.format("   地址：%s\n", spot.getAddress()));
                }
                sb.append("\n");
            }

            return sb.toString();

        } catch (Exception e) {
            log.error("[SearchHotelsTool] Exception: {}", e.getMessage(), e);
            return String.format("住宿信息查询失败：%s", e.getMessage());
        }
    }

    // ==================== 工具定义 ====================

    public ToolSpecRegistry.ToolSpec getToolSpec() {
        return new ToolSpecRegistry.ToolSpec(
            "search_hotels",
            "查询目标城市的住宿信息。当用户询问住宿、酒店、旅馆、民宿时使用。",
            Map.of(
                "type", "object",
                "properties", Map.of(
                    "city", Map.of(
                        "type", "string",
                        "description", "目标城市名"
                    ),
                    "budget", Map.of(
                        "type", "number",
                        "description", "预算上限（元/晚，可选）"
                    ),
                    "level", Map.of(
                        "type", "string",
                        "enum", List.of("economy", "comfort", "luxury"),
                        "description", "住宿档次（可选）"
                    )
                ),
                "required", List.of("city")
            )
        );
    }
}
