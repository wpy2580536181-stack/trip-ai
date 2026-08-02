package com.trip.backend.service.agent.tools;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.service.KnowledgeService;
import com.trip.backend.infra.resilience.CircuitBreaker;
import com.trip.backend.infra.resilience.ToolResilienceWrapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Retrieve Knowledge 工具
 *
 * 对应 Python tools/retrieve_knowledge.py
 *
 * 功能：
 * - 从知识库检索景点、美食、住宿、交通
 * - 分类名归一化（中文 → 英文）
 * - 关键词推断（从 query 推断 category）
 * - poi_cache 读写（仅 attraction/food）
 * - 韧性包装（超时 8s + 熔断 5/30s + fallback）
 */
public class RetrieveKnowledgeTool {

    private static final Logger log = LoggerFactory.getLogger(RetrieveKnowledgeTool.class);

    // 分类映射（中文 → 英文）
    private static final Map<String, String> CATEGORY_MAP = Map.of(
        "景点", "attraction",
        "美食", "food",
        "住宿", "hotel",
        "交通", "transportation"
    );

    // 关键词推断
    private static final Pattern FOOD_KEYWORDS = Pattern.compile("美食|好吃的|餐厅|吃|饭|早饭|午饭|晚饭|早餐|午餐|晚餐");
    private static final Pattern SPOT_KEYWORDS = Pattern.compile("景点|好玩|逛|游览|参观|玩");

    private final KnowledgeService knowledgeService;
    private final ToolResilienceWrapper resilienceWrapper;
    private final CircuitBreaker circuitBreaker;

    public RetrieveKnowledgeTool(KnowledgeService knowledgeService) {
        this.knowledgeService = knowledgeService;
        this.circuitBreaker = CircuitBreaker.getOrCreate("retrieve_knowledge", 5, 30_000);
        this.resilienceWrapper = ToolResilienceWrapper.builder()
            .timeout(8_000)
            .retries(0)
            .fallback("知识库暂时不可用，请基于通用旅行知识回答。")
            .circuitBreaker(circuitBreaker)
            .build();
    }

    /**
     * 执行工具调用
     *
     * @param query 搜索关键词
     * @param city 目标城市
     * @param category 分类（可选：景点/美食/住宿/交通）
     * @return 检索结果字符串
     */
    public String execute(String query, String city, String category) {
        return execute(query, city, category, 5);
    }

    /**
     * 执行工具调用（内部方法）
     */
    String execute(String query, String city, String category, int limit) {
        // 1. 分类归一化
        if (category == null || category.isBlank()) {
            // 从 query 关键词推断
            if (FOOD_KEYWORDS.matcher(query).find()) {
                category = "美食";
            } else if (SPOT_KEYWORDS.matcher(query).find()) {
                category = "景点";
            }
        }

        String dbCategory = CATEGORY_MAP.getOrDefault(category, category);
        String searchCategory = dbCategory != null ? dbCategory : "attraction";

        // 2. 调用检索（带韧性包装）
        try {
            List<Spot> results = resilienceWrapper.execute(() ->
                knowledgeService.searchSpots(query, city, searchCategory, limit)
            );

            if (results == null || results.isEmpty()) {
                return String.format("知识库中没有找到 %s 的相关信息。", city);
            }

            // 格式化结果
            StringBuilder sb = new StringBuilder();
            sb.append(String.format("在 %s 找到 %d 个结果：\n\n", city, results.size()));

            for (int i = 0; i < results.size(); i++) {
                Spot spot = results.get(i);
                sb.append(String.format("%d. **%s**\n", i + 1, spot.getName()));
                if (spot.getDescription() != null && !spot.getDescription().isBlank()) {
                    sb.append(String.format("   %s\n", spot.getDescription()));
                }
                if (spot.getRating() != null) {
                    sb.append(String.format("   评分：%.1f\n", spot.getRating()));
                }
                if (spot.getAvgCost() != null) {
                    sb.append(String.format("   人均消费：%s\n", spot.getAvgCost()));
                }
                if (spot.getAddress() != null && !spot.getAddress().isBlank()) {
                    sb.append(String.format("   地址：%s\n", spot.getAddress()));
                }
                sb.append("\n");
            }

            return sb.toString();

        } catch (Exception e) {
            log.error("[RetrieveKnowledgeTool] Exception: {}", e.getMessage(), e);
            return String.format("知识库检索失败：%s", e.getMessage());
        }
    }

    // ==================== 工具定义 ====================

    public ToolSpecRegistry.ToolSpec getToolSpec() {
        return new ToolSpecRegistry.ToolSpec(
            "retrieve_knowledge",
            "从旅行知识库检索景点、美食、住宿、交通等真实信息。当用户询问某个城市具体的景点推荐、美食、交通、住宿时，必须调用此工具获取真实数据。",
            Map.of(
                "type", "object",
                "properties", Map.of(
                    "query", Map.of(
                        "type", "string",
                        "description", "搜索关键词，描述你想了解的景点主题"
                    ),
                    "city", Map.of(
                        "type", "string",
                        "description", "目标城市名"
                    ),
                    "category", Map.of(
                        "type", "string",
                        "enum", List.of("景点", "美食", "住宿", "交通"),
                        "description", "景点类型（可选）"
                    )
                ),
                "required", List.of("query", "city")
            )
        );
    }
}
