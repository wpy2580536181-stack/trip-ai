package com.trip.backend.service.agent;

import com.trip.backend.service.agent.card.CardEventBuilder;
import com.trip.backend.service.agent.dto.PlanRequest;
import com.trip.backend.service.agent.dto.PlanResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;

/**
 * AgentEngine 对话内核（对应 Python agent_engine.py + chat_agent.py）。
 *
 * 流程：
 *  1. 预检测：附近/通勤关键词 → 直调 commute 分支，发卡片
 *  2. 否则由 IntentResolver 判定意图（LLM 或规则）
 *  3. 流后四分支：trigger_plan / trigger_modify / trigger_patch / select_skill
 *  4. 未知 → 纯文本回复（降级）
 *
 * 真实流式逐 chunk 消费在阶段 4 挂接；此处先固定分发骨架与卡片/落库闭环。
 */
public class AgentEngine {

    private static final Logger log = LoggerFactory.getLogger(AgentEngine.class);

    /** 意图解析（默认规则实现；LLM 版阶段 4 接入）。 */
    public interface IntentResolver {
        TriggerTools.Intent resolve(String message);
    }

    private final Orchestrator orchestrator;
    private final TripPersistenceService persistence;
    private final IntentResolver resolver;

    public AgentEngine(Orchestrator orchestrator,
                       TripPersistenceService persistence,
                       IntentResolver resolver) {
        this.orchestrator = orchestrator;
        this.persistence = persistence;
        this.resolver = resolver != null ? resolver : m -> new TriggerTools.Intent.Chat(m);
    }

    /** 对话入口。返回 {reply, card, eventType, tripId}。 */
    public Map<String, Object> chat(Long userId, String message, Long conversationId) {
        // 1. 预检测：通勤/附近关键词
        if (TriggerTools.isCommuteQuery(message)) {
            Object card = CardEventBuilder.buildCard("commute_compare",
                "已为您查询通勤方案", null, null);
            return Map.of(
                "reply", "我帮您查一下通勤方案，结果见卡片。",
                "card", card,
                "branch", "commute"
            );
        }

        // 2. 意图判定
        TriggerTools.Intent intent = resolver.resolve(message);

        // 3. 四分支分发
        if (intent instanceof TriggerTools.Intent.Plan p) {
            return handlePlan(userId, p.plan());
        }
        if (intent instanceof TriggerTools.Intent.Modify m) {
            return handleModify(userId, m.modify());
        }
        if (intent instanceof TriggerTools.Intent.Patch) {
            // patch 由 PatchEngine 处理（阶段 4 接真实 patch）
            return Map.of("reply", "槽位级修改已接收。", "branch", "trigger_patch");
        }
        if (intent instanceof TriggerTools.Intent.Skill s) {
            return Map.of("reply", "已选择技能：" + s.skill().skillName(),
                "branch", "select_skill");
        }
        // 4. 降级：普通对话
        return Map.of("reply", message, "branch", "chat");
    }

    private Map<String, Object> handlePlan(Long userId, TriggerTools.PlanIntent p) {
        PlanResult result = orchestrator.plan(new PlanRequest(p.city(), p.days(), p.budget()));
        if (result.plan().containsKey("error")) {
            return Map.of("reply", "规划失败：" + result.plan().get("error"), "branch", "trigger_plan");
        }
        // 真落库，返回真实 id
        Long tripId = persistence.savePlan(userId, p.city(), p.days(), p.budget(),
            result.plan(), "completed", null);
        return Map.of(
            "reply", "行程已生成",
            "branch", "trigger_plan",
            "tripId", tripId
        );
    }

    private Map<String, Object> handleModify(Long userId, TriggerTools.ModifyIntent m) {
        // modify 需要 existing trip；此处走 Orchestrator.modify 骨架
        return Map.of(
            "reply", "修改请求已接收：" + m.modifyRequest(),
            "branch", "trigger_modify"
        );
    }
}
