package com.trip.backend.infra.skill;

import java.util.Optional;

/**
 * SelectorTool：技能选择工具
 *
 * 对应 Python: selector_tool.py (select_skill / extract_select_skill_call)
 *
 * 功能：
 * - select_skill 工具方法：供主 LLM 通过 tool calling 表达技能选择意图
 * - extractSelectSkillCall 解析：从 LLM 响应中提取 select_skill 调用
 *
 * 设计对齐：
 * - Anthropic 规范：L1 目录常驻主 LLM 上下文，由主 LLM 自行判断是否激活技能
 * - 主 LLM 调用此工具 = 选中技能 → 节点执行技能
 *
 * TODO: Java 版工具系统尚在建设中，此类暂时作为占位符
 *       D9-7 ChatAgent 改造时完善具体实现
 */
public class SelectorTool {

    /**
     * 选择技能执行（工具方法）
     *
     * 对应 Python @tool select_skill()
     *
     * @param skillName 匹配的技能名称（必须来自可用技能目录）
     * @return 技能名称（确认选择）
     */
    public static String selectSkill(String skillName) {
        // TODO: 验证 skillName 是否在 SkillRegistry 中
        return skillName;
    }

    /**
     * 从 LLM 响应中提取 select_skill 工具调用
     *
     * 对应 Python extract_select_skill_call()
     *
     * @param response LLM 响应（TODO: 替换为 ChatResponse 类型）
     * @return 技能名称（若 LLM 调用了 select_skill），否则空 Optional
     */
    public static Optional<String> extractSelectSkillCall(Object response) {
        // TODO: 实现 tool_calls 解析
        // 伪代码：
        // List<ToolCall> toolCalls = response.getToolCalls();
        // for (ToolCall tc : toolCalls) {
        //     if ("select_skill".equals(tc.getName())) {
        //         return Optional.of(tc.getArgs().get("skill_name"));
        //     }
        // }
        return Optional.empty();
    }
}
