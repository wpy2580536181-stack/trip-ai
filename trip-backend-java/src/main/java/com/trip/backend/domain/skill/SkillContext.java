package com.trip.backend.domain.skill;

import java.util.Collections;
import java.util.List;

/**
 * L3 执行上下文：由调用方（AgentEngine）注入
 *
 * 对应 Python: SkillContext (types.py)
 *
 * 用于：
 * - 传递 LLM 实例
 * - 传递可用工具列表
 * - 传递技能注册表
 * - 传递用户输入
 * - 收集披露轨迹（disclosure）
 */
public record SkillContext(
    /** LLM 客户端（用于多轮 tool calling） */
    Object llm,  // TODO: 替换为 LlmClient 接口

    /** 可用工具列表（L3 执行时可用） */
    List<Object> tools,

    /** 技能注册表（嵌套技能调用，可选） */
    Object registry,  // TODO: 替换为 SkillRegistry（D9-3 创建后）

    /** 用户原始输入 */
    String userInput,

    /** 披露轨迹（L1/L2/L3 层级记录） */
    List<String> disclosure
) {
    /**
     * 空上下文（用于测试）
     */
    public SkillContext() {
        this(null, Collections.emptyList(), null, "", Collections.emptyList());
    }

    /**
     * 添加披露记录
     */
    public SkillContext withDisclosure(String record) {
        List<String> newDisclosure = new java.util.ArrayList<>(disclosure);
        newDisclosure.add(record);
        return new SkillContext(llm, tools, registry, userInput, newDisclosure);
    }
}
