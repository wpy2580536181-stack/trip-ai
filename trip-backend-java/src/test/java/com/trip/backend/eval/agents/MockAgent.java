package com.trip.backend.eval.agents;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.TokenUsage;
import com.trip.backend.eval.types.ToolCall;
import com.trip.backend.eval.types.PoiMatch;
import java.util.List;
import java.util.Map;
import java.util.ArrayList;

/**
 * Mock Agent（用于测试）
 * <p>
 * 根据 fixture 的期望生成逼真的 mock 输出
 */
public class MockAgent {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /**
     * 执行 mock agent（返回基于 fixture 期望的 JSON 输出）
     */
    public static AgentOutput run(Fixture fixture) {
        try {
            // 生成符合 fixture 期望的 mock 输出
            String mockJson = generateMockItinerary(fixture);
            String mockText = generateMockText(fixture);

            AgentOutput output = new AgentOutput();
            output.setText(mockText);
            output.setJson(OBJECT_MAPPER.readValue(mockJson, Map.class));
            output.setToolCalls(generateMockToolCalls(fixture));
            output.setTokens(new TokenUsage(100, 50, 150, 80));  // 模拟 token 消耗
            output.setDurationMs(100);

            return output;

        } catch (Exception e) {
            AgentOutput output = new AgentOutput();
            output.setError("Mock agent failed: " + e.getMessage());
            return output;
        }
    }

    /**
     * 生成 mock 文本（包含关键词）
     */
    private static String generateMockText(Fixture fixture) {
        StringBuilder text = new StringBuilder();
        text.append("为您推荐").append(fixture.getExpected().getCity()).append("行程：\n\n");

        // 添加必须包含的关键词
        if (fixture.getExpected().getMustContainKeywords() != null) {
            text.append(String.join("、", fixture.getExpected().getMustContainKeywords())).append("\n");
        }

        // 添加推荐景点
        if (fixture.getExpected().getSpotNames() != null && !fixture.getExpected().getSpotNames().isEmpty()) {
            text.append("主要景点：").append(String.join("、", fixture.getExpected().getSpotNames())).append("\n");
        }

        // 避免使用不应该出现的关键词
        text.append("请注意避开：");
        List<String> avoidKeywords = fixture.getExpected().getMustNotContainKeywords();
        if (avoidKeywords != null && !avoidKeywords.isEmpty()) {
            text.append(String.join("、", avoidKeywords));
        } else {
            text.append("无特殊禁忌");
        }
        text.append("\n");

        return text.toString();
    }

    /**
     * 生成 mock 工具调用
     */
    private static List<ToolCall> generateMockToolCalls(Fixture fixture) {
        List<ToolCall> toolCalls = new ArrayList<>();

        if (fixture.getExpected().getToolCalls() != null) {
            for (var rule : fixture.getExpected().getToolCalls()) {
                // 根据期望的工具调用规则生成 mock 调用
                int count = rule.getMinCalls() > 0 ? rule.getMinCalls() : 0;
                for (int i = 0; i < count; i++) {
                    ToolCall tc = new ToolCall();
                    tc.setName(rule.getName());
                    tc.setArgs(Map.of("query", "mock query"));
                    tc.setResult(Map.of("status", "success"));
                    tc.setTimestamp(String.valueOf(System.currentTimeMillis()));
                    toolCalls.add(tc);
                }
            }
        }

        return toolCalls;
    }

    /**
     * 生成符合 fixture 期望的行程 JSON
     */
    private static String generateMockItinerary(Fixture fixture) {
        try {
            int days = fixture.getExpected().getDays() > 0 ? fixture.getExpected().getDays() : 3;
            String city = fixture.getExpected().getCity();
            if (city.isEmpty()) city = "成都";

            List<String> spotNames = fixture.getExpected().getSpotNames();

            // 构建行程结构
            StringBuilder json = new StringBuilder();
            json.append("{");
            json.append("\"city\":\"").append(city).append("\",");
            json.append("\"days\":").append(days).append(",");
            json.append("\"dailyItinerary\":[");

            for (int i = 0; i < days; i++) {
                if (i > 0) json.append(",");
                json.append("{");
                json.append("\"day\":").append(i + 1).append(",");

                // 添加景点（如果有期望的 spot names）
                if (spotNames != null && !spotNames.isEmpty()) {
                    String spot = spotNames.get(i % spotNames.size());
                    json.append("\"spots\":[\"").append(spot).append("\"],");
                }

                json.append("\"activities\":[");
                json.append("{\"time\":\"morning\",\"description\":\"游览景点\",\"estimated_cost\":200},");
                json.append("{\"time\":\"afternoon\",\"description\":\"体验活动\",\"estimated_cost\":300},");
                json.append("{\"time\":\"evening\",\"description\":\"晚餐\",\"estimated_cost\":150}");
                json.append("]");
                json.append("}");
            }

            json.append("],");
            json.append("\"budgetBreakdown\":{\"accommodation\":1200,\"food\":900,\"transport\":400,\"tickets\":500,\"totalBudget\":3000},");
            json.append("\"totalBudget\":3000");
            json.append("}");

            return json.toString();

        } catch (Exception e) {
            return "{\"city\":\"成都\",\"days\":3,\"dailyItinerary\":[],\"error\":\"" + e.getMessage() + "\"}";
        }
    }
}
