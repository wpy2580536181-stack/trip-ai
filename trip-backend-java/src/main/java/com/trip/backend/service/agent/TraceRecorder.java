package com.trip.backend.service.agent;

import com.trip.backend.domain.entity.AgentStep;
import com.trip.backend.domain.repository.AgentStepRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * TraceRecorder 链路追踪记录器
 *
 * 职责：
 * - 记录 agent_steps（conversation_id/message_id/step_name/step_type/status/duration_ms）
 * - 失败降级 warn 不影响主流程
 */
@Service
public class TraceRecorder {

    private static final Logger log = LoggerFactory.getLogger(TraceRecorder.class);

    private final AgentStepRepository agentStepRepository;

    public TraceRecorder(AgentStepRepository agentStepRepository) {
        this.agentStepRepository = agentStepRepository;
    }

    /**
     * 记录步骤
     *
     * @param conversationId 会话 ID
     * @param messageId 消息 ID（可选）
     * @param stepName 步骤名
     * @param stepType 步骤类型
     * @param status 状态
     * @param durationMs 耗时（毫秒）
     * @param metadata 元数据
     */
    public void recordStep(Long conversationId, Long messageId, String stepName,
                          String stepType, String status, long durationMs, Map<String, Object> metadata) {
        try {
            AgentStep step = new AgentStep();
            step.setConversationId(conversationId);
            step.setMessageId(messageId);
            step.setStepName(stepName);
            step.setStepType(stepType);
            step.setStatus(status);
            step.setDurationMs(durationMs);
            // TODO: metadata 字段需在 AgentStep 实体中添加

            agentStepRepository.save(step);

            log.debug("[TraceRecorder] Recorded step: conversationId={}, stepName={}, status={}",
                conversationId, stepName, status);
        } catch (Exception e) {
            // 降级：记录失败不影响主流程
            log.warn("[TraceRecorder] Failed to record step: {}", stepName, e);
        }
    }

    /**
     * 批量记录步骤
     *
     * @param steps 步骤列表
     */
    public void recordSteps(List<AgentStep> steps) {
        try {
            agentStepRepository.saveAll(steps);
            log.debug("[TraceRecorder] Batch recorded {} steps", steps.size());
        } catch (Exception e) {
            log.warn("[TraceRecorder] Failed to batch record steps", e);
        }
    }
}
