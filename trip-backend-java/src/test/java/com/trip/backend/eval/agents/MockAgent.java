package com.trip.backend.eval.agents;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.TokenUsage;

import java.util.List;
import java.util.Map;

/**
 * Mock Agent（用于测试）
 * <p>
 * 从 fixture 中读取预定义的 mock 输出
 */
public class MockAgent {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /**
     * 执行 mock agent（返回预设的 JSON 输出）
     */
    public static AgentOutput run(Fixture fixture) {
        try {
            // 这里简化处理：返回一个默认的 mock 输出
            // 实际应该从 fixture 文件或配置中读取预定义的输出

            // 生成一个简单的 mock 输出
            String mockJson = generateMockItinerary(fixture);

            AgentOutput output = new AgentOutput();
            output.setText("Mock agent response for: " + fixture.getId());
            output.setJson(OBJECT_MAPPER.readValue(mockJson, Map.class));
            output.setToolCalls(List.of());  // mock agent 不调用工具
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
     * 生成简单的 mock 行程 JSON
     */
    private static String generateMockItinerary(Fixture fixture) {
        try {
            int days = fixture.getExpected().getDays() > 0 ? fixture.getExpected().getDays() : 3;
            String city = fixture.getExpected().getCity();
            if (city.isEmpty()) city = "成都";

            // 构建简单的行程结构
            StringBuilder json = new StringBuilder();
            json.append("{");
            json.append("\"city\":\"").append(city).append("\",");
            json.append("\"days\":").append(days).append(",");
            json.append("\"dailyItinerary\":[");

            for (int i = 0; i < days; i++) {
                if (i > 0) json.append(",");
                json.append("{");
                json.append("\"day\":").append(i + 1).append(",");
                json.append("\"morning\":{\"spot\":\"景点A\",\"city\":\"").append(city).append("\"},");
                json.append("\"afternoon\":{\"spot\":\"景点B\",\"city\":\"").append(city).append("\"},");
                json.append("\"evening\":{\"spot\":\"景点C\",\"city\":\"").append(city).append("\"}");
                json.append("}");
            }

            json.append("],");
            json.append("\"budgetBreakdown\":{\"totalBudget\":3000},");
            json.append("\"totalBudget\":3000");
            json.append("}");

            return json.toString();

        } catch (Exception e) {
            return "{\"city\":\"成都\",\"days\":3,\"dailyItinerary\":[]}";
        }
    }
}
