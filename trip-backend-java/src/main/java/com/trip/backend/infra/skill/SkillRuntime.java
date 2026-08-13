package com.trip.backend.infra.skill;

import com.trip.backend.domain.skill.SkillContext;
import com.trip.backend.domain.skill.SkillResult;

import java.util.HashMap;
import java.util.Map;

/**
 * SkillRuntime：技能执行辅助（构建上下文 + 执行入口）
 *
 * 对应 Python: runtime.py (build_skill_context / run_skill_if_selected)
 *
 * 功能：
 * - buildSkillContext()：组装 SkillContext（注入 LLM + 底层工具 + registry）
 * - runSkillIfSelected()：检测 select_skill 调用并执行
 * - runSelectedSkill()：[DEPRECATED] 旧接口，保留向后兼容
 *
 * 设计：
 * - 新架构：主 LLM 绑定 select_skill 工具，由主 LLM 自行判断是否激活技能
 * - 旧架构：独立 route_skill 路由调用（已废弃）
 */
public class SkillRuntime {

    /**
     * 为一次技能执行组装 SkillContext
     *
     * @param llm       LLM 客户端（TODO: 替换为 LlmClient 接口）
     * @param registry  SkillRegistry（L1/L2/L3 中枢）
     * @param userInput 用户原始输入
     * @param tools      可用工具列表（TODO: 替换为 Tool 接口）
     * @return SkillContext
     */
    public static SkillContext buildSkillContext(
            Object llm,
            SkillRegistry registry,
            String userInput,
            Object... tools  // TODO: 替换为 List<Tool>
    ) {
        return new SkillContext(
            llm,
            java.util.Arrays.asList(tools),
            registry,
            userInput != null ? userInput : "",
            new java.util.ArrayList<>()
        );
    }

    /**
     * 检测主 LLM 响应中的 select_skill 工具调用，命中则执行技能
     *
     * 新架构（对齐 Anthropic 规范）：主 LLM 绑定 select_skill 工具 + 域工具，
     * 单次调用即可同时完成路由 + 规划。LLM 调用 select_skill = 选中技能；
     * 不调用 = LLM 自行处理（节点使用 LLM 的文本输出）。
     *
     * @param registry   SkillRegistry
     * @param llm        LLM 客户端（TODO: 替换为 LlmClient）
     * @param response   主 LLM 的响应（可能含 tool_calls，TODO: 替换为 ChatResponse）
     * @param userInput  传给技能执行的原始输入
     * @param kwargs     技能入参（如 city/days/budget/departure_city）
     * @return SkillResult（命中且执行）或 null（未选中技能）
     */
    public static SkillResult runSkillIfSelected(
            SkillRegistry registry,
            Object llm,
            Object response,  // TODO: 替换为 ChatResponse
            String userInput,
            Map<String, Object> kwargs
    ) {
        // 参数校验
        if (registry == null || llm == null || response == null) {
            return null;
        }

        // 提取 select_skill 工具调用
        String skillName = extractSelectSkillCall(response);
        if (skillName == null || skillName.isEmpty()) {
            return null;
        }

        // 验证技能是否已注册
        if (registry.get(skillName) == null) {
            return null;
        }

        // 构建上下文并执行
        SkillContext ctx = buildSkillContext(llm, registry, userInput);
        return registry.execute(skillName, ctx, kwargs);
    }

    /**
     * 从 LLM 响应中提取 select_skill 工具调用
     *
     * @param response LLM 响应（TODO: 替换为 ChatResponse）
     * @return 技能名称（若 LLM 调用了 select_skill），否则 null
     */
    private static String extractSelectSkillCall(Object response) {
        // TODO: 实现 tool_calls 解析（对应 Python extract_select_skill_call）
        // 暂时返回 null（D9-5 SelectorTool 实现后补全）
        return null;
    }

    /**
     * [DEPRECATED] L1 路由 + L2/L3 执行的便捷封装
     *
     * 已废弃：新架构使用 runSkillIfSelected()，由主 LLM 通过 select_skill
     * 工具自行判断是否激活技能，无需独立路由调用。
     *
     * @param registry SkillRegistry
     * @param llm      LLM 客户端
     * @param query    用于选技能的查询文本
     * @param userInput 传给技能执行的原始输入
     * @param kwargs   技能入参
     * @return SkillResult 或 null
     */
    @Deprecated
    public static SkillResult runSelectedSkill(
            SkillRegistry registry,
            Object llm,
            String query,
            String userInput,
            Map<String, Object> kwargs
    ) {
        if (registry == null || llm == null) {
            return null;
        }

        // TODO: 使用已废弃的 route_skill（内部会回退到 select() 关键字匹配）
        // 暂时返回 null
        return null;
    }
}
