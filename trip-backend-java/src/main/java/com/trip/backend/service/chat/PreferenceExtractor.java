package com.trip.backend.service.chat;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

/**
 * 偏好提取器（对应 Python services/chat/preference_extractor.py）。
 *
 * J-D12：extractPreferences 真调 LLM——最近 10 条消息 content[:200] 拼接；
 * mergePreferences 增量合并（interests/avoid 去重追加、pace/budget_level/companions 覆盖）。
 */
@Service
public class PreferenceExtractor {

    private static final Logger log = LoggerFactory.getLogger(PreferenceExtractor.class);

    /** LLM 提取端口（生产 = LlmClient；测试 = stub）。 */
    public interface LlmPort {
        /** 输入截断后的对话文本，返回提取到的偏好 Map。 */
        Map<String, Object> extract(String truncatedConversation);
    }

    /**
     * 真调 LLM 提取偏好。
     *
     * @param recentMessages 最近消息内容（自动取最后 10 条、每条 [:200]）
     */
    public Map<String, Object> extractPreferences(Long userId, List<String> recentMessages, LlmPort llm) {
        if (recentMessages == null || recentMessages.isEmpty() || llm == null) {
            return Map.of();
        }
        try {
            List<String> last10 = recentMessages.size() > 10
                ? recentMessages.subList(recentMessages.size() - 10, recentMessages.size())
                : recentMessages;
            StringBuilder content = new StringBuilder();
            for (String msg : last10) {
                String t = msg.length() > 200 ? msg.substring(0, 200) : msg;
                content.append(t).append("\n");
            }
            Map<String, Object> extracted = llm.extract(content.toString());
            return extracted != null ? extracted : Map.of();
        } catch (Exception e) {
            log.warn("[PreferenceExtractor] 提取失败 userId={}: {}", userId, e.getMessage());
            return Map.of();
        }
    }

    /** 增量合并偏好。 */
    public Map<String, Object> mergePreferences(Map<String, Object> existing, Map<String, Object> extracted) {
        Map<String, Object> merged = new java.util.LinkedHashMap<>(existing);
        mergeListField(merged, extracted, "interests");
        mergeListField(merged, extracted, "avoid");
        for (String key : List.of("pace", "budget_level", "companions")) {
            if (extracted.containsKey(key)) {
                merged.put(key, extracted.get(key));
            }
        }
        return merged;
    }

    private void mergeListField(Map<String, Object> merged, Map<String, Object> extracted, String field) {
        Object existingValue = merged.get(field);
        Object extractedValue = extracted.get(field);
        if (extractedValue instanceof List<?> extractedList && !extractedList.isEmpty()) {
            if (existingValue instanceof List<?> existingList) {
                LinkedHashSet<Object> mergedList = new LinkedHashSet<>(existingList);
                mergedList.addAll(extractedList);
                merged.put(field, List.copyOf(mergedList));
            } else {
                merged.put(field, extractedList);
            }
        }
    }
}
