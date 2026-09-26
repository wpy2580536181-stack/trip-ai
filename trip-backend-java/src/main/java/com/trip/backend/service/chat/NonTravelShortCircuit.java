package com.trip.backend.service.chat;

import org.springframework.stereotype.Component;

import java.util.regex.Pattern;

/**
 * 非旅行问题短路检测（对应 Python services/agent/nodes/chat_planner.py）
 *
 * 职责：
 * - 检测用户消息是否非旅行相关
 * - 短路逻辑：chunk → complete(usage=0) → end，不调用 LLM 或工具
 *
 * TODO: D8 阶段替换为真实意图分类器
 */
@Component
public class NonTravelShortCircuit {

    // 非旅行关键词（简单正则匹配）
    private static final Pattern NON_TRAVEL_PATTERN = Pattern.compile(
        "^(你好|hello|hi|hey|谢谢|thank|天气|weather|新闻|news|股票|stock|基金|fund|"
        + "笑话|joke|八卦|gossip|音乐|music|电影|movie|电视剧|tv|"
        + "你好呀|嗨|hi呀|在吗|在不在|"
        + "python|java|javascript|list|tuple|dict|函数|代码|编程|算法|报错|bug|sql|regex|怎么写|栈|线程|编译|变量|数组|loop|tuple)",
        Pattern.CASE_INSENSITIVE
    );

    /**
     * 检测是否是非旅行问题
     *
     * @param userMessage 用户消息
     * @return true 表示非旅行问题，需要短路
     */
    public boolean isNonTravel(String userMessage) {
        if (userMessage == null || userMessage.isBlank()) {
            return true;
        }

        String trimmed = userMessage.trim();
        return NON_TRAVEL_PATTERN.matcher(trimmed).find();
    }

    /**
     * 生成短路响应（mock）
     *
     * @param userMessage 用户消息
     * @return 短路事件序列（JSON 字符串数组）
     */
    public String[] generateShortCircuitEvents(String userMessage) {
        String response = "抱歉，我是旅行规划助手，只能帮助您解决旅游、出行、行程规划相关的问题。请问您有什么旅游出发目的地的计划需要帮助吗？";

        return new String[] {
            String.format("{\"type\":\"chunk\",\"data\":{\"content\":%s}}", escapeJson(response)),
            String.format("{\"type\":\"complete\",\"data\":{\"usage\":{\"prompt\":0,\"completion\":0,\"total\":0,\"cached\":0}}}"),
            String.format("{\"type\":\"end\"}")
        };
    }

    private static String escapeJson(String value) {
        return "\"" + value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            + "\"";
    }
}
