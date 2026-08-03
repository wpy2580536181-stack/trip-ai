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
            // 检查是否为反例场景（city 为空或 days 为 0）
            boolean isCounterExample = fixture.getExpected().getCity().isEmpty() ||
                                       fixture.getExpected().getDays() == 0;

            // 检查是否为细节问题场景（json_valid: false）
            boolean isDetailQuestion = !fixture.getExpected().isJsonValid() &&
                                       !fixture.getExpected().getCity().isEmpty() &&
                                       fixture.getExpected().getDays() > 0;

            String mockJson;
            String mockText;

            if (isCounterExample) {
                // 反例：不生成行程
                mockJson = "{}";
                mockText = generateCounterExampleText(fixture);
            } else if (isDetailQuestion) {
                // 细节问题：生成文本回答，不生成 JSON 行程
                mockJson = "{}";
                mockText = generateDetailAnswerText(fixture);
            } else {
                // 正常场景：生成行程
                mockJson = generateMockItinerary(fixture);
                mockText = generateMockText(fixture);
            }

            AgentOutput output = new AgentOutput();
            output.setText(mockText);
            output.setJson(OBJECT_MAPPER.readValue(mockJson, Map.class));
            output.setToolCalls(generateMockToolCalls(fixture));
            output.setTokens(new TokenUsage(100, 50, 150, 80));
            output.setDurationMs(100);

            return output;

        } catch (Exception e) {
            AgentOutput output = new AgentOutput();
            output.setError("Mock agent failed: " + e.getMessage());
            return output;
        }
    }

    /**
     * 生成反例场景文本（不提供行程）
     */
    private static String generateCounterExampleText(Fixture fixture) {
        StringBuilder text = new StringBuilder();
        text.append("关于您的需求，我可以提供一些建议：\n\n");

        // 添加必须包含的关键词
        if (fixture.getExpected().getMustContainKeywords() != null) {
            text.append(String.join("、", fixture.getExpected().getMustContainKeywords())).append("\n");
        }

        text.append("\n不过，我目前无法为您提供具体的行程规划，建议您：\n");
        text.append("1. 明确目的地城市\n");
        text.append("2. 确定出行天数\n");
        text.append("3. 设定预算范围\n");
        text.append("\n有了这些信息，我就能为您制定详细的旅行计划啦！");

        return text.toString();
    }

    /**
     * 生成细节问题回答文本
     */
    private static String generateDetailAnswerText(Fixture fixture) {
        StringBuilder text = new StringBuilder();
        text.append("关于您的问题：\n\n");

        // 添加必须包含的关键词
        if (fixture.getExpected().getMustContainKeywords() != null) {
            for (String keyword : fixture.getExpected().getMustContainKeywords()) {
                text.append(keyword).append("\n");
            }
        }

        text.append("\n详情如下：\n");
        text.append("- 码头：西湖游船码头位于湖滨一公园\n");
        text.append("- 船票：成人票 50 元/人，学生票 25 元/人\n");
        text.append("- 时间：上午 8:00 - 下午 6:00\n");

        return text.toString();
    }

    /**
     * 生成 mock 文本（包含关键词）
     */
    private static String generateMockText(Fixture fixture) {
        StringBuilder text = new StringBuilder();

        // 检查是否为反例场景（city 为空或 days 为 0）
        boolean isCounterExample = fixture.getExpected().getCity().isEmpty() ||
                                   fixture.getExpected().getDays() == 0;

        if (isCounterExample) {
            // 反例：不生成行程，只提供建议或说明
            text.append("关于您的需求，我可以提供一些建议：\n\n");

            // 添加必须包含的关键词
            if (fixture.getExpected().getMustContainKeywords() != null) {
                text.append(String.join("、", fixture.getExpected().getMustContainKeywords())).append("\n");
            }

            text.append("\n不过，我目前无法为您提供具体的行程规划，建议您：\n");
            text.append("1. 明确目的地城市\n");
            text.append("2. 确定出行天数\n");
            text.append("3. 设定预算范围\n");
            text.append("\n有了这些信息，我就能为您制定详细的旅行计划啦！");
        } else {
            // 正常场景：生成行程推荐
            text.append("为您推荐").append(fixture.getExpected().getCity()).append("行程：\n\n");

            // 添加必须包含的关键词
            if (fixture.getExpected().getMustContainKeywords() != null) {
                text.append(String.join("、", fixture.getExpected().getMustContainKeywords())).append("\n");
            }

            // 添加推荐景点
            if (fixture.getExpected().getSpotNames() != null && !fixture.getExpected().getSpotNames().isEmpty()) {
                text.append("主要景点：").append(String.join("、", fixture.getExpected().getSpotNames())).append("\n");
            }

            // 特殊处理：宠物友好提示
            if (fixture.getInput().getMessage().contains("宠物") ||
                fixture.getInput().getMessage().contains("狗") ||
                fixture.getInput().getMessage().contains("猫")) {
                text.append("宠物友好提示：请携带牵引绳，注意防疫，及时清理宠物便便。\n");
                text.append("（已为您排除：动物园、野生动物园、海洋馆等宠物禁入场所）\n");
            }
        }

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

                // 根据 must_not_contain_keywords 过滤活动描述
                List<String> avoidKeywords = fixture.getExpected().getMustNotContainKeywords();
                String morningActivity = getActivityDescription("morning", avoidKeywords, city);
                String afternoonActivity = getActivityDescription("afternoon", avoidKeywords, city);
                String eveningActivity = getActivityDescription("evening", avoidKeywords, city);

                json.append("\"activities\":[");
                json.append(morningActivity).append(",");
                json.append(afternoonActivity).append(",");
                json.append(eveningActivity);
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

    /**
     * 获取活动描述（避开禁用关键词）
     */
    private static String getActivityDescription(String timeOfDay, List<String> avoidKeywords, String city) {
        if (avoidKeywords == null || avoidKeywords.isEmpty()) {
            return getDefaultActivity(timeOfDay);
        }

        // 宠物友好活动建议
        Map<String, List<String>> petFriendlyActivities = Map.of(
            "morning", List.of("公园散步", "江边晨跑", "城市观光", "历史街区漫步"),
            "afternoon", List.of("博物馆参观", "艺术区探索", "步行街购物", "特色街区游览"),
            "evening", List.of("夜景欣赏", "特色餐厅用餐", "文化体验", "休闲娱乐")
        );

        List<String> activities = petFriendlyActivities.getOrDefault(timeOfDay, List.of("观光"));

        // 过滤包含禁用关键词的活动
        List<String> filtered = activities.stream()
            .filter(activity -> avoidKeywords.stream().noneMatch(activity::contains))
            .toList();

        String selected = filtered.isEmpty() ? getDefaultActivity(timeOfDay) : filtered.get(0);

        return "{\"time\":\"" + timeOfDay + "\",\"description\":\"" + selected + "\",\"estimated_cost\":200}";
    }

    private static String getDefaultActivity(String timeOfDay) {
        return switch (timeOfDay) {
            case "morning" -> "{\"time\":\"morning\",\"description\":\"游览景点\",\"estimated_cost\":200}";
            case "afternoon" -> "{\"time\":\"afternoon\",\"description\":\"体验活动\",\"estimated_cost\":300}";
            case "evening" -> "{\"time\":\"evening\",\"description\":\"晚餐\",\"estimated_cost\":150}";
            default -> "{\"time\":\"activity\",\"description\":\"观光\",\"estimated_cost\":200}";
        };
    }
}
