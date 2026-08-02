package com.trip.backend.service.tasks;

import com.trip.backend.service.agent.TraceRecorder;
import com.trip.backend.service.tasks.TaskRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Map;

/**
 * Post-Chat Followup 任务
 *
 * 对应 Python services/tasks/post_chat.py
 *
 * 功能：
 * - 对话压缩（compress_conversation）
 * - 关键决策记录
 * - 偏好提取
 *
 * job_id = post_chat:followup:{conversation_id}
 */
@Service
public class PostChatFollowupTask {

    private static final Logger log = LoggerFactory.getLogger(PostChatFollowupTask.class);

    private final TaskRegistry taskRegistry;
    private final TraceRecorder traceRecorder;

    public PostChatFollowupTask(TaskRegistry taskRegistry, TraceRecorder traceRecorder) {
        this.taskRegistry = taskRegistry;
        this.traceRecorder = traceRecorder;
    }

    /**
     * 入队 followup 任务
     *
     * @param conversationId 会话 ID
     * @param userId 用户 ID
     * @return Job ID
     */
    public String enqueueFollowup(Long conversationId, Long userId) {
        String jobId = String.format("post_chat:followup:%d", conversationId);

        // 注册任务
        taskRegistry.register("post_chat_followup", jobId, ctx -> {
            try {
                log.info("[PostChatFollowup] Starting followup: conversationId={}", conversationId);

                // 1. 压缩对话
                // TODO: D12 实现后补充
                String summary = compressConversation(conversationId);

                // 2. 关键决策记录（is_planning 时）
                // TODO: D12 实现后补充

                // 3. 偏好提取
                // TODO: D12 实现后补充

                log.info("[PostChatFollowup] Followup completed: conversationId={}", conversationId);
                return Map.of("conversation_id", conversationId, "status", "ok");

            } catch (Exception e) {
                log.error("[PostChatFollowup] Failed: conversationId={}", conversationId, e);
                throw e; // 触发重试
            }
        });

        // 入队
        taskRegistry.enqueue("post_chat_followup", jobId);

        return jobId;
    }

    /**
     * 压缩对话摘要
     */
    private String compressConversation(Long conversationId) {
        // TODO: D12 实现后补充（调用 LLM 生成摘要）
        return "Conversation summary for " + conversationId;
    }
}
