package com.trip.backend.service.agent;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;

/**
 * Planner 输出 JSON 修复（对应 Python nodes/validate.repair_json）。
 *
 * 三层：
 *  1. 直接解析
 *  2. 去 markdown 代码块后解析
 *  3. 提取最外层 { ... } 解析
 */
public final class RepairJson {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private RepairJson() {}

    /** 解析失败返回 null。 */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        // 1. 直接
        Map<String, Object> direct = tryParse(raw);
        if (direct != null) {
            return direct;
        }
        // 2. 去 markdown 代码块
        String stripped = raw.trim();
        if (stripped.startsWith("```")) {
            stripped = stripped.replaceFirst("^```[a-zA-Z]*", "");
            int fence = stripped.lastIndexOf("```");
            if (fence > 0) {
                stripped = stripped.substring(0, fence);
            }
            Map<String, Object> m2 = tryParse(stripped);
            if (m2 != null) {
                return m2;
            }
        }
        // 3. 提取最外层 {}
        int first = stripped.indexOf('{');
        int last = stripped.lastIndexOf('}');
        if (first >= 0 && last > first) {
            return tryParse(stripped.substring(first, last + 1));
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> tryParse(String s) {
        try {
            Object o = MAPPER.readValue(s, Object.class);
            if (o instanceof Map) {
                return (Map<String, Object>) o;
            }
        } catch (Exception ignored) {
        }
        return null;
    }
}
