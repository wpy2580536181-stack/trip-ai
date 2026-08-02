package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.ResearchBundle;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * RepairJson 修复服务
 *
 * 对应 Python services/agent/repair_json.py
 *
 * 功能：
 * - 提取最外层 {}
 * - 剥离 markdown 代码块
 */
@Service
public class RepairJson {

    private static final Logger log = LoggerFactory.getLogger(RepairJson.class);

    /**
     * 修复 JSON
     *
     * @param raw 原始文本
     * @return 修复后的 JSON 字符串
     */
    public String repair(String raw) {
        if (raw == null || raw.isBlank()) {
            return "{}";
        }

        String text = raw.trim();

        // 1. 剥离 markdown 代码块
        text = stripMarkdownCodeBlocks(text);

        // 2. 提取最外层 {}
        text = extractOuterObject(text);

        return text;
    }

    /**
     * 剥离 markdown 代码块
     */
    private String stripMarkdownCodeBlocks(String text) {
        // 移除 ```json ... ```
        text = text.replaceAll("```json\\s*", "");
        text = text.replaceAll("```\\s*", "");
        return text.trim();
    }

    /**
     * 提取最外层对象 {}
     */
    private String extractOuterObject(String text) {
        int start = text.indexOf('{');
        int end = text.lastIndexOf('}');

        if (start >= 0 && end > start) {
            return text.substring(start, end + 1);
        }

        // 没有 {}，返回原文本（包装成对象）
        return "{\"raw\":\"" + escapeJson(text) + "\"}";
    }

    /**
     * JSON 转义
     */
    private String escapeJson(String value) {
        return value.replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t");
    }
}
