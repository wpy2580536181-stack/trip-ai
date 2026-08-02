package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * PlannerAgent 计划代理
 *
 * 职责：
 * - 生成行程计划
 * - 主 LLM 失败切 fallback_llm
 * - PlannerInput.feedback 注入
 */
@Service
public class PlannerAgent {

    private static final Logger log = LoggerFactory.getLogger(PlannerAgent.class);

    private final LlmClient llmClient;
    private final LlmClient fallbackLlmClient;

    public PlannerAgent(LlmClient llmClient, LlmClient fallbackLlmClient) {
        this.llmClient = llmClient;
        this.fallbackLlmClient = fallbackLlmClient;
    }

    private TokenUsage lastUsage = TokenUsage.empty();

    public TokenUsage getLastUsage() {
        return lastUsage;
    }

    /**
     * 生成计划
     *
     * @param input 计划输入
     * @return 计划（JSON 字符串）
     */
    public CompletableFuture<Map<String, Object>> plan(PlannerInput input) {
        log.info("[PlannerAgent] Generating plan, feedback={}",
            input.feedback() != null ? "present" : "none");

        return CompletableFuture.supplyAsync(() -> {
            try {
                // 构建 prompt
                String prompt = buildPrompt(input);

                // 调用 LLM
                ChatResponse response = llmClient.chat(prompt).join();

                lastUsage = response.usage() != null ? response.usage() : TokenUsage.empty();

                // 解析 JSON
                return parseJsonResponse(response.content());

            } catch (Exception e) {
                log.error("[PlannerAgent] Primary LLM failed, trying fallback", e);

                try {
                    // 主 LLM 失败，切 fallback
                    ChatResponse fallbackResponse = fallbackLlmClient.chat(buildPrompt(input)).join();
                    lastUsage = fallbackResponse.usage() != null ? fallbackResponse.usage() : TokenUsage.empty();
                    return parseJsonResponse(fallbackResponse.content());
                } catch (Exception ex) {
                    log.error("[PlannerAgent] Fallback LLM also failed", ex);
                    throw new RuntimeException("PlannerAgent failed: " + ex.getMessage(), ex);
                }
            }
        });
    }

    /**
     * 构建 prompt
     */
    private String buildPrompt(PlannerInput input) {
        // TODO: D7 实现后补充完整 prompt
        return "Generate a travel plan for " + input.research();
    }

    /**
     * 解析 JSON 响应
     */
    private Map<String, Object> parseJsonResponse(String content) {
        try {
            // 提取 JSON（移除 markdown 代码块等）
            String json = extractJson(content);
            return new com.fasterxml.jackson.databind.ObjectMapper().readValue(json, Map.class);
        } catch (Exception e) {
            log.error("[PlannerAgent] Failed to parse JSON response", e);
            throw new RuntimeException("Failed to parse plan JSON", e);
        }
    }

    /**
     * 提取 JSON（最外层 {}）
     */
    private String extractJson(String content) {
        // 简单提取：找第一个 { 到最后一个 }
        int start = content.indexOf('{');
        int end = content.lastIndexOf('}');
        if (start >= 0 && end > start) {
            return content.substring(start, end + 1);
        }
        return content;
    }
}
