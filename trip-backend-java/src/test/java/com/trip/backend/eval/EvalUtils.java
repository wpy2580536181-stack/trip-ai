package com.trip.backend.eval;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.EvalResult;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.FixtureExpected;
import com.trip.backend.eval.types.FixtureInput;
import com.trip.backend.eval.types.ToolCall;
import com.trip.backend.eval.types.ToolCallRule;
import com.trip.backend.eval.types.ToolCall;
import com.trip.backend.eval.types.ToolCallRule;

import java.util.List;
import java.util.Map;

/**
 * 工具类：Eval 框架辅助方法
 */
public class EvalUtils {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /**
     * 判断文本是否包含关键词（支持 all/any 模式）
     */
    public static boolean containsKeywords(String text, List<String> keywords, String mode) {
        if (keywords == null || keywords.isEmpty()) {
            return true;
        }

        if ("any".equals(mode)) {
            return keywords.stream().anyMatch(text::contains);
        } else {
            // "all" mode (default)
            return keywords.stream().allMatch(text::contains);
        }
    }

    /**
     * 判断文本是否不包含关键词
     */
    public static boolean notContainsKeywords(String text, List<String> keywords) {
        if (keywords == null || keywords.isEmpty()) {
            return true;
        }
        return keywords.stream().noneMatch(text::contains);
    }

    /**
     * 解析 JSON 字符串
     */
    public static Object parseJson(String text) {
        try {
            return OBJECT_MAPPER.readValue(text, Object.class);
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * 从 AgentOutput 提取行程 JSON
     */
    public static Object extractItinerary(AgentOutput output) {
        if (output.getJson() != null) {
            return output.getJson();
        }
        if (output.getText() != null) {
            return parseJson(output.getText());
        }
        return null;
    }

    /**
     * 从行程 JSON 中提取天数
     */
    public static Integer extractDays(Object itinerary) {
        if (itinerary instanceof Map) {
            Object days = ((Map<?, ?>) itinerary).get("days");
            if (days instanceof Number) {
                return ((Number) days).intValue();
            }
        }
        return null;
    }

    /**
     * 从行程 JSON 中提取每天活动数
     */
    public static List<Integer> extractActivitiesPerDay(Object itinerary) {
        // TODO: 实现提取逻辑
        return List.of();
    }

    /**
     * 检查工具调用是否满足规则
     */
    public static boolean checkToolCalls(List<ToolCall> toolCalls,
                                         List<ToolCallRule> rules) {
        if (rules == null || rules.isEmpty()) {
            return true;
        }

        for (ToolCallRule rule : rules) {
            long count = toolCalls.stream()
                    .filter(tc -> rule.getName().equals(tc.getName()))
                    .count();

            if (rule.getMinCalls() > 0 && count < rule.getMinCalls()) {
                return false;
            }
            if (rule.getMaxCalls() > 0 && count > rule.getMaxCalls()) {
                return false;
            }
        }
        return true;
    }
}
