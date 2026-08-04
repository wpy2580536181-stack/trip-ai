package com.trip.backend.service;

import com.trip.backend.domain.entity.AgentStep;
import com.trip.backend.domain.repository.AgentStepRepository;
import com.trip.backend.domain.repository.ConversationRepository;
import com.trip.backend.domain.repository.MessageRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Admin service（简化版）
 * - Agent trace 查询
 * - MCP stats 查询
 */
@Service
public class AdminService {

    private final AgentStepRepository agentStepRepository;
    private final MessageRepository messageRepository;
    private final ConversationRepository conversationRepository;

    public AdminService(AgentStepRepository agentStepRepository,
                       MessageRepository messageRepository,
                       ConversationRepository conversationRepository) {
        this.agentStepRepository = agentStepRepository;
        this.messageRepository = messageRepository;
        this.conversationRepository = conversationRepository;
    }

    /**
     * 获取 Agent 执行轨迹
     */
    @Transactional(readOnly = true)
    public List<AgentStep> getAgentTrace(Long messageId) {
        return agentStepRepository.findByMessageIdOrderByStepAsc(messageId);
    }

    /**
     * 获取 Agent 执行轨迹摘要列表
     */
    @Transactional(readOnly = true)
    public List<Map<String, Object>> getAgentTraceSummary(Long conversationId, int limit) {
        // 简化版：返回空列表
        return List.of();
    }

    /**
     * 获取 MCP 进程状态和调用指标
     */
    public Map<String, Object> getMcpStats() {
        // TODO: 集成 MCP 指标
        return Map.of(
            "alive", false,
            "metrics", Map.of(
                "calls", 0L,
                "successes", 0L,
                "failures", 0L,
                "cacheHits", 0L,
                "circuitOpenCount", 0,
                "avgDurationMs", 0.0
            )
        );
    }
}
