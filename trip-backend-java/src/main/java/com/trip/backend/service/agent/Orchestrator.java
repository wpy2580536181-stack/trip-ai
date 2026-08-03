package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.PlanRequest;
import com.trip.backend.service.agent.dto.PlanResult;
import com.trip.backend.service.llm.LlmClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * Orchestrator 简化版（G4 完整实现）
 *
 * 直接调用 LlmClient 生成行程计划
 */
@Service
public class Orchestrator {

    private static final Logger log = LoggerFactory.getLogger(Orchestrator.class);
    private final LlmClient llmClient;

    public Orchestrator(LlmClient llmClient) {
        this.llmClient = llmClient;
    }

    /**
     * 生成行程计划
     */
    public PlanResult plan(PlanRequest request) {
        long startTime = System.currentTimeMillis();
        log.info("[Orchestrator] 开始规划: city={}, days={}, budget={}",
            request.city(), request.days(), request.budget());

        try {
            // 构建 prompt
            String prompt = buildPrompt(request);

            // 调用 LLM
            List<LlmClient.ChatMessage> messages = List.of(
                new LlmClient.ChatMessage("system", "你是一个专业的旅行规划师，请输出 JSON 格式的行程计划。"),
                new LlmClient.ChatMessage("user", prompt)
            );

            LlmClient.ChatResponse response = llmClient.invoke(messages);
            String content = response.content();

            log.info("[Orchestrator] LLM 响应: {}...", content.substring(0, Math.min(50, content.length())));

            // 解析 plan（简化版：提取 JSON）
            Map<String, Object> plan = parsePlan(content, request);

            long durationMs = System.currentTimeMillis() - startTime;
            log.info("[Orchestrator] 规划完成: duration={}ms", durationMs);

            return PlanResult.of(plan);

        } catch (Exception e) {
            log.error("[Orchestrator] 规划失败", e);
            long durationMs = System.currentTimeMillis() - startTime;
            return PlanResult.error("规划失败: " + e.getMessage());
        }
    }

    /**
     * 构建 prompt
     */
    private String buildPrompt(PlanRequest request) {
        return String.format(
            "请为 %s 规划 %d 日游行程，预算 %d 元。\n" +
            "请输出 JSON 格式，包含以下字段：\n" +
            "{\n" +
            "  \"city\": \"%s\",\n" +
            "  \"days\": %d,\n" +
            "  \"totalBudget\": %d,\n" +
            "  \"dailyItinerary\": [\n" +
            "    {\n" +
            "      \"day\": 1,\n" +
            "      \"morning\": {\"spot\": \"景点名\", \"duration\": \"2小时\", \"ticket\": \"免费\"},\n" +
            "      \"afternoon\": {\"spot\": \"景点名\", \"duration\": \"3小时\", \"ticket\": \"50元\"},\n" +
            "      \"evening\": {\"spot\": \"景点名\", \"duration\": \"2小时\", \"ticket\": \"免费\"}\n" +
            "    }\n" +
            "  ],\n" +
            "  \"budgetBreakdown\": {\n" +
            "    \"accommodation\": 0,\n" +
            "    \"food\": 0,\n" +
            "    \"transportation\": 0,\n" +
            "    \"tickets\": 0,\n" +
            "    \"other\": 0\n" +
            "  },\n" +
            "  \"tips\": []\n" +
            "}",
            request.city(), request.days(), request.budget(),
            request.city(), request.days(), request.budget()
        );
    }

    /**
     * 解析 LLM 响应为 plan（简化版）
     */
    private Map<String, Object> parsePlan(String content, PlanRequest request) {
        try {
            log.debug("[Orchestrator] LLM 原始响应 (前 200 字符): {}",
                content.substring(0, Math.min(200, content.length())));

            // 尝试提取 JSON
            int start = content.indexOf('{');
            int end = content.lastIndexOf('}');
            if (start >= 0 && end > start) {
                String json = content.substring(start, end + 1);
                Map<String, Object> plan = new com.fasterxml.jackson.databind.ObjectMapper()
                    .readValue(json, Map.class);

                log.info("[Orchestrator] LLM 返回 plan: city={}, days={}, keys={}",
                    plan.get("city"), plan.get("days"), plan.keySet());

                // 确保必填字段存在（对齐 Python 版本）
                plan.putIfAbsent("city", request.city());
                plan.putIfAbsent("days", request.days());
                plan.putIfAbsent("totalBudget", request.budget());
                plan.putIfAbsent("dailyItinerary", List.of());
                plan.putIfAbsent("budgetBreakdown", Map.of(
                    "accommodation", 0,
                    "food", 0,
                    "transportation", 0,
                    "tickets", 0,
                    "other", 0
                ));
                plan.putIfAbsent("tips", List.of());
                plan.putIfAbsent("warnings", List.of());

                return plan;
            }
        } catch (Exception e) {
            log.warn("[Orchestrator] JSON 解析失败，使用默认结构", e);
        }

        // 返回默认结构（对齐 Python 版本）
        return Map.of(
            "city", request.city(),
            "days", request.days(),
            "totalBudget", request.budget(),
            "dailyItinerary", List.of(),
            "budgetBreakdown", Map.of(
                "accommodation", 0,
                "food", 0,
                "transportation", 0,
                "tickets", 0,
                "other", 0
            ),
            "tips", List.of("提前订票", "注意天气"),
            "warnings", List.of()
        );
    }
}
