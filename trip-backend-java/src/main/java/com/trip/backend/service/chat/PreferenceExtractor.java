package com.trip.backend.service.chat;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * 偏好提取器
 *
 * 对应 Python services/chat/preference_extractor.py
 *
 * 功能：
 * - 从最近 10 条消息提取偏好
 * - 增量合并（interests/avoid 去重追加、pace/budget_level/companions 覆盖）
 */
@Service
public class PreferenceExtractor {

    private static final Logger log = LoggerFactory.getLogger(PreferenceExtractor.class);

    /**
     * 提取偏好
     *
     * @param userId 用户 ID
     * @param recentMessages 最近消息内容列表（最多 10 条）
     * @return 偏好更新映射
     */
    public Map<String, Object> extractPreferences(Long userId, List<String> recentMessages) {
        try {
            // 拼接消息（每条约 200 字符）
            StringBuilder content = new StringBuilder();
            for (String msg : recentMessages) {
                String truncated = msg.length() > 200 ? msg.substring(0, 200) : msg;
                content.append(truncated).append("\n");
            }

            // TODO: D12 实现后补充 LLM 调用提取偏好
            // 目前返回空映射
            log.debug("[PreferenceExtractor] Extracting preferences for user: {}", userId);
            return Map.of();

        } catch (Exception e) {
            log.warn("[PreferenceExtractor] Failed to extract preferences: userId={}", userId, e);
            return Map.of();
        }
    }

    /**
     * 增量合并偏好
     *
     * @param existing 现有偏好
     * @param extracted 新提取的偏好
     * @return 合并后的偏好
     */
    public Map<String, Object> mergePreferences(Map<String, Object> existing, Map<String, Object> extracted) {
        Map<String, Object> merged = new java.util.LinkedHashMap<>(existing);

        // interests/avoid：去重追加
        mergeListField(merged, extracted, "interests");
        mergeListField(merged, extracted, "avoid");

        // pace/budget_level/companions：覆盖
        for (String key : List.of("pace", "budget_level", "companions")) {
            if (extracted.containsKey(key)) {
                merged.put(key, extracted.get(key));
            }
        }

        return merged;
    }

    /**
     * 合并列表字段（去重追加）
     */
    private void mergeListField(Map<String, Object> merged, Map<String, Object> extracted, String field) {
        Object existingValue = merged.get(field);
        Object extractedValue = extracted.get(field);

        if (extractedValue instanceof List<?> extractedList && !extractedList.isEmpty()) {
            if (existingValue instanceof List<?> existingList) {
                // 去重追加
                java.util.LinkedHashSet<Object> mergedList = new java.util.LinkedHashSet<>(existingList);
                mergedList.addAll(extractedList);
                merged.put(field, List.copyOf(mergedList));
            } else {
                merged.put(field, extractedList);
            }
        }
    }
}
