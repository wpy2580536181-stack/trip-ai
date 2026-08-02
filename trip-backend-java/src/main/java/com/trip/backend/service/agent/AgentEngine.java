package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * AgentEngine 代理引擎
 *
 * 职责：
 * - chat()/recommend() 入口
 * - 共享 llm/tool_cache/skill_registry
 * - embedding fail-closed + warmup 启动
 */
@Service
public class AgentEngine {

    private static final Logger log = LoggerFactory.getLogger(AgentEngine.class);

    private final LlmClient llmClient;
    private final ChatAgent chatAgent;
    private final Orchestrator orchestrator;

    public AgentEngine(LlmClient llmClient, ChatAgent chatAgent, Orchestrator orchestrator) {
        this.llmClient = llmClient;
        this.chatAgent = chatAgent;
        this.orchestrator = orchestrator;
    }

    /**
     * 聊天入口
     *
     * @param userId 用户 ID
     * @param message 用户消息
     * @param conversationId 会话 ID
     * @param tripId 行程 ID（可选）
     * @return 响应
     */
    public CompletableFuture<ChatResponse> chat(Long userId, String message, Long conversationId, Long tripId) {
        log.info("[AgentEngine] chat: userId={}, message={}", userId, message);

        return chatAgent.chat(userId, message, conversationId, tripId);
    }

    /**
     * 推荐入口
     *
     * @param request 推荐请求
     * @return 推荐结果
     */
    public CompletableFuture<PlanResult> recommend(PlanRequest request) {
        log.info("[AgentEngine] recommend: city={}, days={}, budget={}",
            request.city(), request.days(), request.budget());

        return orchestrator.plan(request);
    }

    /**
     * 启动 warmup（embedding 预热）
     */
    public void warmup() {
        try {
            log.info("[AgentEngine] Warmup started");
            // TODO: D8 实现后补充 embedding warmup
            log.info("[AgentEngine] Warmup completed");
        } catch (Exception e) {
            log.error("[AgentEngine] Warmup failed", e);
        }
    }
}
