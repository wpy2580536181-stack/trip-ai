package com.trip.backend.domain.skill;

import java.util.List;

/**
 * L1 目录层：常驻上下文的轻量元信息
 *
 * 对应 Python: SkillCatalog (types.py)
 *
 * 用于：
 * - 注入系统提示词（供 LLM 判断是否激活技能）
 * - select() 关键词匹配（name/tags/Trigger）
 */
public record SkillCatalog(
    /** 技能名称（唯一标识） */
    String name,

    /** 技能描述（一句话说明用途） */
    String description,

    /** 标签列表（用于关键词匹配） */
    List<String> tags,

    /** 技能类型："agent" | "tool" */
    String kind
) {
    /**
     * 默认 kind 为 "agent"
     */
    public SkillCatalog(String name, String description, List<String> tags) {
        this(name, description, tags, "agent");
    }

    /**
     * 转换为提示词片段
     *
     * @return 格式：- **name** [kind]：description（tags: tag1, tag2）
     */
    public String toPromptFragment() {
        StringBuilder sb = new StringBuilder();
        sb.append("- **").append(name).append("** [").append(kind).append("]：").append(description);

        if (tags != null && !tags.isEmpty()) {
            sb.append("（tags: ").append(String.join(", ", tags)).append("）");
        }

        return sb.toString();
    }
}
