package com.trip.backend.service.llm;

/**
 * 场景优先级（对应 Python provider_router/scenario.py）
 */
public enum Scenario {
    PLANNING,    // 行程规划：deepseek → kimi → agnese
    CHAT,        // 对话：agnese → kimi → deepseek
    RESEARCH     // 研究：agnese → deepseek → kimi
}
