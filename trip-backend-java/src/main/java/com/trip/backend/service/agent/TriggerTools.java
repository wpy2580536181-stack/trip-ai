package com.trip.backend.service.agent;

import java.util.Map;

/**
 * 四个升级意图信号（对应 Python trigger_tools.py）。
 *
 * 这些不是真正的工具执行，而是 LLM 判定用户意图后产生的信号，
 * 由 AgentEngine 流后分发给 Orchestrator / PatchEngine / SkillRegistry。
 */
public final class TriggerTools {

    private TriggerTools() {}

    /** 全量规划。 */
    public record PlanIntent(String city, int days, int budget) {}

    /** 修改已有行程（自然语言）。 */
    public record ModifyIntent(String modifyRequest, String targetDays) {}

    /** Slot 级精确修改。 */
    public record PatchIntent(String op, int day, String period,
                              String spotName, String periodB) {}

    /** 选技能。 */
    public record SkillIntent(String skillName, Map<String, Object> kwargs) {}

    /** 意图解析结果（要么是某个 trigger，要么是普通文本）。 */
    public sealed interface Intent {
        record Plan(PlanIntent plan) implements Intent {}
        record Modify(ModifyIntent modify) implements Intent {}
        record Patch(PatchIntent patch) implements Intent {}
        record Skill(SkillIntent skill) implements Intent {}
        record Chat(String text) implements Intent {}
    }

    /** 预检测：附近/通勤关键词直走 commute 分支（不进 LLM）。 */
    public static boolean isCommuteQuery(String message) {
        if (message == null) return false;
        String m = message.toLowerCase();
        return m.contains("附近") || m.contains("通勤") || m.contains("怎么去")
            || m.contains("地铁") || m.contains("公交") || m.contains("怎么走");
    }
}
