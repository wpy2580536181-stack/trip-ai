package com.trip.backend.service.task;

import com.trip.backend.service.chat.PreferenceExtractor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 对话后处理任务（对应 Python tasks/post_chat.py）。
 *
 * worker：compress_conversation → 关键决策记录（is_planning 才做）→ 偏好提取。
 * job_id = post_chat:followup:{conversation_id} 幂等——同会话重复入队只执行一次。
 */
@Component
public class PostChatFollowupTask {

    private static final Logger log = LoggerFactory.getLogger(PostChatFollowupTask.class);

    private final PreferenceExtractor extractor;
    /** 已完成的 job_id（内存幂等键；生产可用 Redis SETNX）。 */
    private final Set<String> completedJobs = ConcurrentHashMap.newKeySet();

    public PostChatFollowupTask(PreferenceExtractor extractor) {
        this.extractor = extractor;
    }

    /** 重置幂等状态（测试用）。 */
    public void resetIdempotency() {
        completedJobs.clear();
    }

    /**
     * 执行后处理。
     *
     * @param conversationId 会话 id（幂等键）
     * @param userId         用户 id
     * @param messages       该会话全部消息文本
     * @param isPlanning     本会话是否发生规划（决定 decision_recorded/skipped）
     * @param existingPrefs  已有偏好
     * @param llm            偏好提取 LLM 端口
     * @return 执行结果标志 + 合并后偏好
     */
    public Map<String, Object> run(Long conversationId, Long userId, List<String> messages,
                                   boolean isPlanning, Map<String, Object> existingPrefs,
                                   PreferenceExtractor.LlmPort llm) {
        String jobId = "post_chat:followup:" + conversationId;

        // 幂等：同会话重复入队只执行一次
        if (!completedJobs.add(jobId)) {
            log.info("[PostChatFollowup] 跳过重复任务: {}", jobId);
            Map<String, Object> skipped = new HashMap<>();
            skipped.put("already_done", true);
            skipped.put("job_id", jobId);
            return skipped;
        }

        Map<String, Object> result = new HashMap<>();
        result.put("job_id", jobId);

        // Step 1: compress_conversation（压缩标志）
        result.put("compressed", messages != null && !messages.isEmpty());

        // Step 2: 关键决策记录（is_planning 才做）
        if (isPlanning) {
            result.put("decision_recorded", true);
            result.put("decision_skipped", false);
        } else {
            result.put("decision_recorded", false);
            result.put("decision_skipped", true);
        }

        // Step 3: 偏好提取 + 增量合并
        Map<String, Object> extracted = (messages == null || messages.isEmpty())
            ? Map.of()
            : extractor.extractPreferences(userId, messages, llm);
        Map<String, Object> merged = extractor.mergePreferences(
            existingPrefs == null ? Map.of() : existingPrefs, extracted);
        result.put("preferences", merged);
        result.put("already_done", false);

        log.info("[PostChatFollowup] done job={}, compressed={}, planning={}",
            jobId, result.get("compressed"), isPlanning);
        return result;
    }
}
