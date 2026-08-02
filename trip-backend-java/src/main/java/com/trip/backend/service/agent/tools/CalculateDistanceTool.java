package com.trip.backend.service.agent.tools;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.service.KnowledgeService;
import com.trip.backend.service.CommuteService;
import com.trip.backend.infra.resilience.CircuitBreaker;
import com.trip.backend.infra.resilience.ToolResilienceWrapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;

/**
 * Calculate Distance 工具
 *
 * 对应 Python tools/calculate_distance.py
 *
 * 功能：
 * - 计算两个城市之间的交通距离、时间和费用
 * - car 模式：走高德路网（失败回退 Haversine）
 * - train / flight 模式：直线距离 + 经验估算
 * - 韧性包装（超时 5s + 重试 1 + 熔断 + fallback）
 */
public class CalculateDistanceTool {

    private static final Logger log = LoggerFactory.getLogger(CalculateDistanceTool.class);

    // 主要城市经纬度（用于 Haversine 回退）
    private static final Map<String, double[]> CITY_COORDS = Map.ofEntries(
        Map.entry("北京", new double[]{39.9042, 116.4074}),
        Map.entry("上海", new double[]{31.2304, 121.4737}),
        Map.entry("广州", new double[]{23.1291, 113.2644}),
        Map.entry("深圳", new double[]{22.5431, 114.0579}),
        Map.entry("成都", new double[]{30.5728, 104.0668}),
        Map.entry("杭州", new double[]{30.2741, 120.1551}),
        Map.entry("武汉", new double[]{30.5928, 114.3055}),
        Map.entry("西安", new double[]{34.3416, 108.9398}),
        Map.entry("重庆", new double[]{29.4316, 106.9123}),
        Map.entry("南京", new double[]{32.0603, 118.7969})
    );

    private final CommuteService commuteService;
    private final ToolResilienceWrapper resilienceWrapper;
    private final CircuitBreaker circuitBreaker;

    public CalculateDistanceTool(CommuteService commuteService) {
        this.commuteService = commuteService;
        this.circuitBreaker = CircuitBreaker.getOrCreate("calculate_distance", 5, 30_000);
        this.resilienceWrapper = ToolResilienceWrapper.builder()
            .timeout(5_000)
            .retries(1)
            .fallback("距离估算暂时不可用。")
            .circuitBreaker(circuitBreaker)
            .build();
    }

    /**
     * 执行工具调用
     *
     * @param fromCity 出发城市
     * @param toCity 目的地城市
     * @param mode 交通方式（train/car/flight）
     * @return 距离信息字符串
     */
    public String execute(String fromCity, String toCity, String mode) {
        String travelMode = (mode != null && !mode.isBlank()) ? mode : "car";

        try {
            if ("car".equals(travelMode)) {
                // car 模式：走高德路网
                return executeCarMode(fromCity, toCity);
            } else {
                // train / flight 模式：直线距离 + 经验估算
                return executeEstimateMode(fromCity, toCity, travelMode);
            }
        } catch (Exception e) {
            log.error("[CalculateDistanceTool] Exception: {}", e.getMessage(), e);
            return String.format("距离计算失败：%s", e.getMessage());
        }
    }

    /**
     * Car 模式：走高德路网（失败回退 Haversine）
     */
    private String executeCarMode(String fromCity, String toCity) {
        try {
            // 调用 CommuteService（高德路网）
            String result = resilienceWrapper.execute(() ->
                commuteService.calculateDistance(fromCity, toCity, "car")
            );

            if (result != null && !result.isBlank()) {
                return result;
            }

            // 回退：Haversine
            log.warn("[CalculateDistanceTool] Car mode failed, fallback to Haversine");
            return haversineEstimate(fromCity, toCity, "car");

        } catch (Exception e) {
            log.warn("[CalculateDistanceTool] Car mode exception, fallback to Haversine: {}", e.getMessage());
            return haversineEstimate(fromCity, toCity, "car");
        }
    }

    /**
     * Train / Flight 模式：直线距离 + 经验估算
     */
    private String executeEstimateMode(String fromCity, String toCity, String mode) {
        return haversineEstimate(fromCity, toCity, mode);
    }

    /**
     * Haversine 估算
     */
    private String haversineEstimate(String fromCity, String toCity, String mode) {
        double[] from = CITY_COORDS.get(fromCity);
        double[] to = CITY_COORDS.get(toCity);

        if (from == null || to == null) {
            return String.format("无法估算 %s 到 %s 的距离（坐标缺失）。", fromCity, toCity);
        }

        double distanceKm = haversine(from[0], from[1], to[0], to[1]);

        if ("train".equals(mode)) {
            double timeHours = Math.round(distanceKm / 300.0);
            double costMin = Math.round(distanceKm * 0.3);
            double costMax = Math.round(distanceKm * 0.8);
            return String.format("%s → %s（高铁，估算）：\n距离 %.0f 公里\n耗时约 %.0f 小时\n费用 %.0f - %.0f 元",
                fromCity, toCity, distanceKm, timeHours, costMin, costMax);
        } else if ("flight".equals(mode)) {
            double timeHours = Math.round(distanceKm / 800.0);
            double costMin = Math.round(distanceKm * 0.8);
            double costMax = Math.round(distanceKm * 2.0);
            return String.format("%s → %s（飞机，估算）：\n距离 %.0f 公里\n飞行时间约 %.0f 小时\n费用 %.0f - %.0f 元",
                fromCity, toCity, distanceKm, timeHours, costMin, costMax);
        } else {
            // car 默认
            double timeHours = distanceKm / 60.0; // 假设 60km/h
            double cost = distanceKm * 0.6; // 油费 + 过路费
            return String.format("%s → %s（驾车，估算）：\n距离 %.0f 公里\n耗时约 %.1f 小时\n费用约 %.0f 元",
                fromCity, toCity, distanceKm, timeHours, cost);
        }
    }

    /**
     * Haversine 公式计算直线距离
     */
    private static double haversine(double lat1, double lon1, double lat2, double lon2) {
        double R = 6371; // 地球半径（公里）
        double dlat = Math.toRadians(lat2 - lat1);
        double dlon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dlat / 2) * Math.sin(dlat / 2)
            + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
            * Math.sin(dlon / 2) * Math.sin(dlon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    // ==================== 工具定义 ====================

    public ToolSpecRegistry.ToolSpec getToolSpec() {
        return new ToolSpecRegistry.ToolSpec(
            "calculate_distance",
            "计算两个城市之间的交通距离、时间和费用。支持驾车（car）、高铁（train）、飞机（flight）。",
            Map.of(
                "type", "object",
                "properties", Map.of(
                    "from_city", Map.of(
                        "type", "string",
                        "description", "出发城市名"
                    ),
                    "to_city", Map.of(
                        "type", "string",
                        "description", "目的地城市名"
                    ),
                    "mode", Map.of(
                        "type", "string",
                        "enum", List.of("car", "train", "flight"),
                        "description", "交通方式"
                    )
                ),
                "required", List.of("from_city", "to_city")
            )
        );
    }
}
