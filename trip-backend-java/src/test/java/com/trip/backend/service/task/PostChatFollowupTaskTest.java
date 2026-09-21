package com.trip.backend.service.task;

import com.trip.backend.service.chat.PreferenceExtractor;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D12 对话后处理判定：
 *  1. 同 conversation 重复入队只执行一次
 *  2. compressed / decision_recorded / decision_skipped 标志正确
 *  3. mock LLM：interests 去重追加、pace/budget_level 覆盖
 */
class PostChatFollowupTaskTest {

    private final PreferenceExtractor extractor = new PreferenceExtractor();

    /** mock LLM：固定返回 interests + pace。 */
    private static PreferenceExtractor.LlmPort mockLlm(Map<String, Object> out) {
        return text -> out;
    }

    // ---- 判定 1：幂等 ----
    @Test
    void sameConversationRunsOnlyOnce() {
        PostChatFollowupTask task = new PostChatFollowupTask(extractor);
        PreferenceExtractor.LlmPort llm = mockLlm(Map.of("interests", List.of("美食"), "pace", "慢"));

        Map<String, Object> first = task.run(100L, 1L,
            List.of("我想去吃美食"), true, Map.of(), llm);
        assertFalse((boolean) first.get("already_done"), "首次应正常执行");

        Map<String, Object> second = task.run(100L, 1L,
            List.of("我想去吃美食"), true, Map.of(), llm);
        assertTrue((boolean) second.get("already_done"), "重复入队应跳过");
        assertEquals("post_chat:followup:100", second.get("job_id"));
    }

    // ---- 判定 2：标志 ----
    @Test
    void decisionFlagsDependOnPlanning() {
        PostChatFollowupTask task = new PostChatFollowupTask(extractor);
        PreferenceExtractor.LlmPort llm = mockLlm(Map.of());

        // isPlanning=true
        Map<String, Object> planning = task.run(1L, 1L, List.of("a"), true, Map.of(), llm);
        assertTrue((boolean) planning.get("compressed"));
        assertTrue((boolean) planning.get("decision_recorded"));
        assertFalse((boolean) planning.get("decision_skipped"));

        // isPlanning=false（另一会话）
        Map<String, Object> chat = task.run(2L, 1L, List.of("b"), false, Map.of(), llm);
        assertTrue((boolean) chat.get("compressed"));
        assertFalse((boolean) chat.get("decision_recorded"));
        assertTrue((boolean) chat.get("decision_skipped"));
    }

    @Test
    void emptyMessagesNotCompressed() {
        PostChatFollowupTask task = new PostChatFollowupTask(extractor);
        Map<String, Object> r = task.run(3L, 1L, List.of(), false, Map.of(), mockLlm(Map.of()));
        assertFalse((boolean) r.get("compressed"));
    }

    // ---- 判定 3：偏好合并 ----
    @Test
    void preferencesMergeDeduplicateAndOverride() {
        // 已有：interests=[博物馆,历史], pace=快
        Map<String, Object> existing = new java.util.LinkedHashMap<>();
        existing.put("interests", List.of("博物馆", "历史"));
        existing.put("pace", "快");

        // mock LLM 新提取：interests=[美食,博物馆]（博物馆重复）、pace=慢（覆盖）、budget_level=高
        PreferenceExtractor.LlmPort llm = mockLlm(Map.of(
            "interests", List.of("美食", "博物馆"),
            "pace", "慢",
            "budget_level", "高"));

        PostChatFollowupTask task = new PostChatFollowupTask(extractor);
        Map<String, Object> r = task.run(4L, 1L, List.of("消息一"), true, existing, llm);

        @SuppressWarnings("unchecked")
        Map<String, Object> prefs = (Map<String, Object>) r.get("preferences");
        @SuppressWarnings("unchecked")
        List<String> interests = (List<String>) prefs.get("interests");
        // 去重追加：博物馆不重复，新增 美食
        assertEquals(List.of("博物馆", "历史", "美食"), interests,
            "interests 应去重追加: " + interests);
        // pace 覆盖
        assertEquals("慢", prefs.get("pace"), "pace 应被新值覆盖");
        // 新增 budget_level
        assertEquals("高", prefs.get("budget_level"));
    }
}
