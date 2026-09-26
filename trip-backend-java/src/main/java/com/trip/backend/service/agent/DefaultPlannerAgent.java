package com.trip.backend.service.agent;

import com.trip.backend.service.llm.LlmClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * PlannerAgent 默认实现：调 LlmClient 生成行程 JSON。
 * feedback 非空时把 review 意见拼进 user 消息（对应 Python planner_input.feedback）。
 */
@Component
public class DefaultPlannerAgent implements PlannerAgent {

    private static final Logger log = LoggerFactory.getLogger(DefaultPlannerAgent.class);
    private final LlmClient llm;

    public DefaultPlannerAgent(LlmClient llm) {
        this.llm = llm;
    }

    @Override
    public Output run(Input input) {
        String system = "你是专业旅行规划师。请输出纯 JSON 行程计划，不要 markdown 代码块。";
        String user = buildPrompt(input);
        try {
            LlmClient.ChatResponse resp = llm.invoke(List.of(
                LlmClient.ChatMessage.of("system", system),
                LlmClient.ChatMessage.of("user", user)));
            return Output.ok(resp.content());
        } catch (Exception e) {
            log.error("[DefaultPlannerAgent] LLM 调用失败", e);
            return Output.fail("LLM 调用失败: " + e.getMessage());
        }
    }

    private String buildPrompt(Input input) {
        StringBuilder sb = new StringBuilder();
        sb.append(String.format("请为 %s 规划 %d 日游行程，预算 %d 元。\n",
            input.city(), input.days(), input.budget()));
        sb.append("输出 JSON，字段：city/days/totalBudget/dailyItinerary(每天含 day/morning/afternoon/evening，"
            + "每个时段 {spot,duration,ticket})/budgetBreakdown{accommodation,food,transportation,tickets,other}/tips[]。\n");
        if (input.userMessage() != null && !input.userMessage().isBlank()) {
            sb.append("用户特殊需求：").append(input.userMessage()).append("\n");
            sb.append("必须在 tips 中逐条具体回应上述特殊需求（如清真/素食等饮食禁忌、宠物注意事项、"
                + "雨天室内安排、省钱建议、带儿童的午休与充足休息、轻松节奏等），不得遗漏。\n");
        }
        if (input.userMessage() != null && input.userMessage().matches("(?s).*(宠物|狗|猫|金毛|柯基|泰迪).*")) {
            sb.append("宠物出行硬性要求：不得安排动物园、野生动物园、水族馆、海洋馆、美术馆、"
                + "科技馆、展览馆、博物馆等宠物禁入的室内场馆；优先户外公园、滨江步道、"
                + "宠物友好景点；tips 必须明确提示牵绳、携带防疫证明、及时清理宠物便便。\n");
        }
        sb.append("tips 中应结合目的地特色，给出当地代表性美食与休闲（如东京必须提到拉面，"
            + "成都应提到茶馆喝茶）和主要交通方式（如东京必须同时提到“电铁”和地铁通票，"
            + "注意“电铁”二字不能只写“地铁”）等实用建议。\n");
        if (input.bundle() != null) {
            String a = input.bundle().attractions();
            String f = input.bundle().food();
            if (a != null && !a.isBlank()) {
                sb.append("【知识库候选景点，请优先从中选择】\n").append(a).append("\n");
            }
            if (f != null && !f.isBlank()) {
                sb.append("【知识库候选美食】\n").append(f).append("\n");
            }
        }
        if (input.feedback() != null && !input.feedback().isBlank()) {
            sb.append("【上一轮修改意见】").append(input.feedback()).append("\n");
        }
        return sb.toString();
    }
}
