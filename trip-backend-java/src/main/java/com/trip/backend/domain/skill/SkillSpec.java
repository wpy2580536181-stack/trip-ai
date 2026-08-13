package com.trip.backend.domain.skill;

import java.util.Collections;
import java.util.List;

/**
 * L2 规格层：技能被「选中」后才加载的详细定义
 *
 * 对应 Python: SkillSpec (types.py)
 *
 * 设计原则：
 * - L2 激活层 = 整篇 SKILL.md 正文（而非仅结构化片段）
 * - resources 供 L3 按需读取
 */
public record SkillSpec(
    /** 触发条件（关键词/场景描述） */
    String trigger,

    /** 执行指令（LLM 编排流程说明） */
    String instructions,

    /** 输入契约（参数结构/类型） */
    String inputSchema,

    /** 使用示例 */
    String examples,

    /** 整篇 SKILL.md 正文（L2 激活层内容） */
    String body,

    /** L3 资源引用（references/scripts/assets 相对路径） */
    List<String> resources
) {
    /**
     * 空规格（解析失败时返回）
     */
    public SkillSpec() {
        this("", "", "", "", "", Collections.emptyList());
    }

    /**
     * 从 body 派生（无结构化字段时）
     */
    public static SkillSpec fromBody(String body) {
        return new SkillSpec("", "", "", "", body, Collections.emptyList());
    }

    /**
     * 是否为空规格
     */
    public boolean isEmpty() {
        return body == null || body.isEmpty();
    }
}
