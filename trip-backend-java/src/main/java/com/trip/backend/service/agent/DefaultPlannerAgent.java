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
        if (input.feedback() != null && !input.feedback().isBlank()) {
            sb.append("【上一轮修改意见】").append(input.feedback()).append("\n");
        }
        return sb.toString();
    }
}
