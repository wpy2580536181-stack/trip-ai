package com.trip.backend.service.agent.tools;

import com.trip.backend.service.llm.LlmClient;

import java.util.Map;

/**
 * 通勤类工具集合（对应 Python tools/commute.py），3 个工具：
 *  - compute_optimal_commute：通勤路线规划（origin/destinations/mode/city/compare_modes）
 *  - search_commute_tips：地点联想（keywords/city/limit）
 *  - search_nearby_commute_pois：周边 POI（lat/lng/radius/keywords/types/limit）
 *
 * 真实高德路网调用由 J-D6 的 MCP 客户端接入；当前 MCP 未连接时 execute 抛异常，
 * ResilienceWrapper 返回对应 fallback JSON（不抛给 LLM）。
 */
public final class CommuteTools {

    private CommuteTools() {
    }

    /** 通勤路线规划。 */
    public static class ComputeOptimalCommute implements AgentTool {

        @Override
        public String name() {
            return "compute_optimal_commute";
        }

        @Override
        public String description() {
            return "规划从起点到多个候选终点的最优通勤路线，支持驾车/步行/公交/骑行对比。";
        }

        @Override
        public LlmClient.ToolSpec spec() {
            return new LlmClient.ToolSpec(name(), description(),
                """
                {"type":"object",
                 "properties":{
                   "origin":{"type":"object","description":"起点（家/当前位置：name/lat/lng/city/address）"},
                   "destinations":{"type":"array","description":"候选终点列表，可多个择优"},
                   "mode":{"type":"string","description":"出行方式：driving/walking/transit/cycling"},
                   "city":{"type":"string","description":"起点城市（transit 必填）"},
                   "compare_modes":{"type":"boolean","description":"为 true 时横向对比 4 种出行方式"}
                 },
                 "required":["origin","destinations","mode"]}""");
        }

        @Override
        public String execute(Map<String, Object> args) {
            throw new IllegalStateException("MCP 高德路网未连接");
        }

        @Override
        public String fallback() {
            return "{\"error\": \"通勤路线规划暂时不可用，请稍后再试。\"}";
        }
    }

    /** 地点联想/搜索建议。 */
    public static class SearchCommuteTips implements AgentTool {

        @Override
        public String name() {
            return "search_commute_tips";
        }

        @Override
        public String description() {
            return "根据关键词搜索地点联想（如「人民广场」「公司」），返回候选地点。";
        }

        @Override
        public LlmClient.ToolSpec spec() {
            return new LlmClient.ToolSpec(name(), description(),
                """
                {"type":"object",
                 "properties":{
                   "keywords":{"type":"string","description":"要搜索的地点关键词"},
                   "city":{"type":"string","description":"城市名，缩小联想范围"},
                   "limit":{"type":"integer","description":"返回条数，默认 5"}
                 },
                 "required":["keywords"]}""");
        }

        @Override
        public String execute(Map<String, Object> args) {
            throw new IllegalStateException("MCP 高德联想未连接");
        }

        @Override
        public String fallback() {
            return "{\"error\": \"地点联想暂时不可用。\"}";
        }
    }

    /** 周边 POI 搜索。 */
    public static class SearchNearbyPois implements AgentTool {

        @Override
        public String name() {
            return "search_nearby_commute_pois";
        }

        @Override
        public String description() {
            return "按中心点半径搜索周边 POI（地铁站/咖啡等）。";
        }

        @Override
        public LlmClient.ToolSpec spec() {
            return new LlmClient.ToolSpec(name(), description(),
                """
                {"type":"object",
                 "properties":{
                   "lat":{"type":"number","description":"中心点纬度"},
                   "lng":{"type":"number","description":"中心点经度"},
                   "radius":{"type":"integer","description":"搜索半径（米），默认 1000"},
                   "keywords":{"type":"string","description":"关键词，如「地铁站」「咖啡」"},
                   "types":{"type":"string","description":"POI 类型编码"},
                   "limit":{"type":"integer","description":"返回条数，默认 15"}
                 },
                 "required":["lat","lng"]}""");
        }

        @Override
        public String execute(Map<String, Object> args) {
            throw new IllegalStateException("MCP 高德周边搜索未连接");
        }

        @Override
        public String fallback() {
            return "{\"error\": \"周边 POI 查询暂时不可用。\"}";
        }
    }
}
