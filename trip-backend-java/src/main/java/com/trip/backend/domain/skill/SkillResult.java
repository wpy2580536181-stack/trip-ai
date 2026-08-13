package com.trip.backend.domain.skill;

import java.util.Collections;
import java.util.List;

/**
 * 技能执行结果：附带经历的层级披露轨迹
 *
 * 对应 Python: SkillResult (types.py)
 *
 * 用于：
 * - 返回执行状态（ok/error）
 * - 返回执行内容（content）
 * - 记录披露轨迹（便于评估/可观测）
 */
public record SkillResult(
    /** 技能名称 */
    String skill,

    /** 是否执行成功 */
    boolean ok,

    /** 执行结果内容 */
    String content,

    /** 披露轨迹（L1/L2/L3 层级记录） */
    List<String> disclosure,

    /** 错误信息（ok=false 时填充） */
    String error
) {
    /**
     * 成功结果
     */
    public static SkillResult success(String skill, String content) {
        return new SkillResult(skill, true, content, Collections.emptyList(), null);
    }

    /**
     * 失败结果
     */
    public static SkillResult failure(String skill, String error) {
        return new SkillResult(skill, false, "", Collections.emptyList(), error);
    }

    /**
     * 带披露轨迹的成功结果
     */
    public static SkillResult success(String skill, String content, List<String> disclosure) {
        return new SkillResult(skill, true, content, disclosure, null);
    }

    /**
     * 是否为空结果（无内容且无错误）
     */
    public boolean isEmpty() {
        return (content == null || content.isEmpty()) && error == null;
    }

    /**
     * 获取错误信息（ok=false 时有效）
     */
    public String getError() {
        return error != null ? error : "Unknown error";
    }
}
