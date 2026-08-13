package com.trip.backend.service.agent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.domain.skill.SkillContext;
import com.trip.backend.domain.skill.SkillResult;
import com.trip.backend.infra.skill.SelectorTool;
import com.trip.backend.infra.skill.SkillRegistry;
import com.trip.backend.infra.skill.patch.PatchEngine;
import com.trip.backend.infra.skill.patch.PatchError;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * ChatAgent：对话 Agent（职责：LLM 调用 + 工具编排 + 技能执行）
 *
 * 对应 Python: chat_agent.py (ChatAgent)
 *
 * 核心职责：
 * - 持有 LLM 客户端 + 8 个底层工具
 * - chat() 方法：调用 LLM + 工具循环
 * - _run_selected_skill()：检测 select_skill 并执行技能
 * - patch 失败降级 modify
 *
 * TODO: D8 完成后接入真实 LLM 调用
 * TODO: D5 完成后接入 8 个底层工具
 */
public class ChatAgent {

    // TODO: 注入 LLM 客户端（D8 完成后）
    private Object llm;

    // TODO: 注入 8 个底层工具（D5 完成后）
    // 1. retrieveKnowledgeTool
    // 2. searchHotelsTool
    // 3. calculateDistanceTool
    // 4. searchCommuteTipsTool
    // 5. computeOptimalCommuteTool
    // 6. searchNearbyCommutePoisTool
    // 7. meituanQueryTool（需要 MEITUAN_HT_TOKEN 校验）
    // 8. selectSkillTool
    private List<Object> tools = new ArrayList<>();

    // SkillRegistry（用于技能执行）
    private SkillRegistry skillRegistry;

    // PatchEngine（用于槽位级修改）
    private PatchEngine patchEngine;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 构造 ChatAgent
     */
    public ChatAgent(Object llm, SkillRegistry skillRegistry, PatchEngine patchEngine) {
        this.llm = llm;
        this.skillRegistry = skillRegistry;
        this.patchEngine = patchEngine;
    }

    /**
     * 对话入口（TODO: D8 完成真实实现）
     *
     * @param userId      用户 ID
     * @param message     用户消息
     * @param conversationId 会话 ID
     * @return AgentOutput（回复内容 + 元数据）
     */
    public AgentOutput chat(Long userId, String message, Long conversationId) {
        // TODO: D8 实现 LLM 调用 + 工具编排
        return AgentOutput.text("ChatAgent 占位符: " + message);
    }

    /**
     * 执行选中的技能
     *
     * 对应 Python: _run_selected_skill()
     *
     * @param userInput  用户输入
     * @param skillName  技能名称
     * @param kwargs     技能参数
     * @return SkillResult
     */
    public SkillResult runSelectedSkill(String userInput, String skillName, Map<String, Object> kwargs) {
        if (skillRegistry == null || skillName == null) {
            return SkillResult.failure(skillName, "SkillRegistry 未注入或技能名为空");
        }

        // 注入 8 个底层工具 + meituan_query_tool
        SkillContext ctx = new SkillContext(
            llm,
            tools,
            skillRegistry,
            userInput,
            new ArrayList<>()
        );

        return skillRegistry.execute(skillName, ctx, kwargs);
    }

    /**
     * 应用 patch（修改行程）
     *
     * @param trip 原行程 JSON
     * @param op   操作类型
     * @param day  天数
     * @param params 参数
     * @return 修改后的行程
     * @throws PatchError patch 失败
     */
    public JsonNode applyPatch(JsonNode trip, String op, int day, PatchEngine.PatchParams params) throws PatchError {
        return patchEngine.applyPatch(trip, op, day, params);
    }

    // ---- 占位符类型 ----

    /**
     * Agent 输出（占位符）
     */
    public record AgentOutput(String content, Map<String, Object> metadata) {
        public static AgentOutput text(String text) {
            return new AgentOutput(text, new HashMap<>());
        }
    }

    // TODO: 使用实际的 LLM 和 Tool 类型
    // private LlmClient llm;
    // private List<Tool> tools;
}
