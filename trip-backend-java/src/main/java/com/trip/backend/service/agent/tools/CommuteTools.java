package com.trip.backend.service.agent.tools;

import com.trip.backend.infra.resilience.CircuitBreaker;
import com.trip.backend.infra.resilience.ToolResilienceWrapper;
import com.trip.backend.service.CommuteService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;

/**
 * Commute 工具（3 个方法）
 *
 * 对应 Python tools/commute.py
 *
 * 包含：
 * - compute_optimal_commute_tool：计算最优通勤路线（20s + 不缓存）
 * - search_commute_tips_tool：搜索通勤提示（8s + 不缓存）
 * - search_nearby_commute_pois_tool：搜索附近 POI（8s + 不缓存）
 */
public class CommuteTools {

    private static final Logger log = LoggerFactory.getLogger(CommuteTools.class);

    private final CommuteService commuteService;
    private final CircuitBreaker circuitBreaker;

    public CommuteTools(CommuteService commuteService) {
        this.commuteService = commuteService;
        this.circuitBreaker = CircuitBreaker.getOrCreate("commute", 5, 30_000);
    }

    /**
     * 计算最优通勤路线
     *
     * @param origin 起点（name + city）
     * @param destinations 候选终点列表
     * @param mode 出行方式（driving/walking/transit/cycling）
     * @param city 起点城市
     * @param compareModes 是否对比多模式
     * @return 路线信息 JSON
     */
    public String computeOptimalCommute(
            Map<String, String> origin,
            List<Map<String, String>> destinations,
            String mode,
            String city,
            boolean compareModes) {
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(20_000)
            .retries(1)
            .fallback("{\"error\":\"通勤路线规划暂时不可用，请稍后再试。\"}")
            .circuitBreaker(circuitBreaker)
            .build();

        try {
            String result = wrapper.execute(() ->
                commuteService.computeOptimalCommute(origin, destinations, mode, city, compareModes)
            );
            return result != null ? result : "{\"error\":\"路线规划失败\"}";
        } catch (Exception e) {
            log.error("[CommuteTools] compute_optimal_commute failed: {}", e.getMessage(), e);
            return "{\"error\":\"路线规划失败：" + e.getMessage() + "\"}";
        }
    }

    /**
     * 搜索通勤提示（地理编码辅助）
     *
     * @param keywords 搜索关键词
     * @param city 城市名
     * @param limit 返回条数
     * @return 候选地点 JSON 数组
     */
    public String searchCommuteTips(String keywords, String city, int limit) {
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(8_000)
            .retries(1)
            .fallback("[]")
            .circuitBreaker(circuitBreaker)
            .build();

        try {
            String result = wrapper.execute(() ->
                commuteService.searchInputTips(keywords, city, limit)
            );
            return result != null ? result : "[]";
        } catch (Exception e) {
            log.error("[CommuteTools] search_commute_tips failed: {}", e.getMessage(), e);
            return "[]";
        }
    }

    /**
     * 搜索附近通勤 POI
     *
     * @param keywords 搜索关键词
     * @param city 城市名
     * @param limit 返回条数
     * @return POI 列表 JSON 数组
     */
    public String searchNearbyCommutePois(String keywords, String city, int limit) {
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(8_000)
            .retries(1)
            .fallback("[]")
            .circuitBreaker(circuitBreaker)
            .build();

        try {
            String result = wrapper.execute(() ->
                commuteService.searchNearbyPois(keywords, city, limit)
            );
            return result != null ? result : "[]";
        } catch (Exception e) {
            log.error("[CommuteTools] search_nearby_commute_pois failed: {}", e.getMessage(), e);
            return "[]";
        }
    }

    // ==================== 工具定义 ====================

    public ToolSpecRegistry.ToolSpec createToolSpec(String name, String description, Map<String, Object> parameters) {
        return new ToolSpecRegistry.ToolSpec(name, description, parameters);
    }

    public List<ToolSpecRegistry.ToolSpec> getToolSpecs() {
        return List.of(
            createToolSpec(
                "compute_optimal_commute",
                "计算两地之间各种出行方式的最优路线。当用户问「从A到B怎么走」「去XXX怎么坐车」「通勤方案」「打车还是公交」「最快路线」时必调此工具。",
                Map.of(
                    "type", "object",
                    "properties", Map.of(
                        "origin", Map.of(
                            "type", "object",
                            "description", "起点信息"
                        ),
                        "destinations", Map.of(
                            "type", "array",
                            "description", "候选终点列表"
                        ),
                        "mode", Map.of(
                            "type", "string",
                            "enum", List.of("driving", "walking", "transit", "cycling")
                        ),
                        "city", Map.of("type", "string"),
                        "compare_modes", Map.of("type", "boolean")
                    ),
                    "required", List.of("origin", "destinations", "mode")
                )
            ),
            createToolSpec(
                "search_commute_tips",
                "根据关键词联想地点并返回候选坐标（地址解析/地理编码辅助）。",
                Map.of(
                    "type", "object",
                    "properties", Map.of(
                        "keywords", Map.of("type", "string", "description", "要搜索的地点关键词"),
                        "city", Map.of("type", "string", "description", "城市名"),
                        "limit", Map.of("type", "integer", "description", "返回条数", "default", 5)
                    ),
                    "required", List.of("keywords")
                )
            ),
            createToolSpec(
                "search_nearby_commute_pois",
                "搜索附近通勤相关 POI（地铁站、公交站、停车场等）。",
                Map.of(
                    "type", "object",
                    "properties", Map.of(
                        "keywords", Map.of("type", "string"),
                        "city", Map.of("type", "string"),
                        "limit", Map.of("type", "integer", "default", 5)
                    ),
                    "required", List.of("keywords")
                )
            )
        );
    }
}
