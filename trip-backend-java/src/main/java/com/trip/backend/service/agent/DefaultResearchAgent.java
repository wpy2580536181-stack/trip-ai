package com.trip.backend.service.agent;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.service.agent.tools.ToolSpecRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.*;

/**
 * ResearchAgent 真实实现。
 *
 * 通过 retrieve_knowledge 工具检索目标城市的景点 / 美食候选，
 * 收集为 ResearchBundle（候选名集合 + 上下文文本 + 工具调用审计），
 * 供 Planner 基于真实知识库规划、Review 做封闭世界校验。
 */
@Component
public class DefaultResearchAgent implements ResearchAgent {

    private static final Logger log = LoggerFactory.getLogger(DefaultResearchAgent.class);
    private static final ObjectMapper OM = new ObjectMapper();

    private final ToolSpecRegistry registry;

    public DefaultResearchAgent(ToolSpecRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Output run(Input input) {
        String city = input.city();
        log.info("[Research] city={} days={} budget={}", city, input.days(), input.budget());

        boolean petMode = input.userMessage() != null
            && input.userMessage().matches("(?s).*(宠物|狗|猫|金毛|柯基|泰迪).*");
        List<String> petBanned = petMode
            ? List.of("动物园", "野生动物园", "水族馆", "海洋馆", "美术馆", "科技馆", "展览馆", "博物馆")
            : List.of();

        List<String> toolCallNames = new ArrayList<>();
        Set<String> spotNames = new LinkedHashSet<>();

        String attractionsJson = callTool(toolCallNames, Map.of(
            "query", city + " 必去景点 推荐",
            "city", city,
            "category", "景点"));
        String attractions2 = callTool(toolCallNames, Map.of(
            "query", city + " 历史文化 地标",
            "city", city,
            "category", "景点"));
        String foodJson = callTool(toolCallNames, Map.of(
            "query", city + " 特色美食 小吃",
            "city", city,
            "category", "美食"));

        StringBuilder attractions = new StringBuilder();
        appendParsed(attractionsJson, spotNames, attractions, petBanned);
        appendParsed(attractions2, spotNames, attractions, petBanned);
        StringBuilder food = new StringBuilder();
        appendParsed(foodJson, new LinkedHashSet<>(), food, List.of());

        log.info("[Research] 完成: 候选景点 {} 个, 工具调用 {} 次",
            spotNames.size(), toolCallNames.size());

        ResearchBundle bundle = new ResearchBundle(
            Set.copyOf(spotNames),
            attractions.toString(),
            food.toString(),
            "", "", "",
            toolCallNames);
        return Output.ok(bundle);
    }

    /** 调 retrieve_knowledge；任何异常降级为提示文本，不阻断整体流程。 */
    private String callTool(List<String> toolCallNames, Map<String, Object> args) {
        toolCallNames.add("retrieve_knowledge");
        try {
            return registry.call("retrieve_knowledge", args);
        } catch (Exception e) {
            log.warn("[Research] 工具调用失败: {}", e.getMessage());
            return "知识库暂时不可用，请基于通用旅行知识回答。";
        }
    }

    /** 解析检索 JSON 数组：提取候选 name，并保留精简上下文文本。 */
    private void appendParsed(String json, Set<String> nameSink, StringBuilder textSink,
                              Collection<String> excludeNameKeywords) {
        if (json == null || json.isBlank() || !json.trim().startsWith("[")) {
            return;
        }
        try {
            List<Map<String, Object>> list = OM.readValue(json,
                new com.fasterxml.jackson.core.type.TypeReference<List<Map<String, Object>>>() {});
            for (Map<String, Object> item : list) {
                Object name = item.get("name");
                if (name == null) continue;
                String nm = name.toString();
                boolean excluded = excludeNameKeywords.stream().anyMatch(nm::contains);
                if (excluded) {
                    log.info("[Research] 宠物场景过滤禁入场所: {}", nm);
                    continue;
                }
                {
                    nameSink.add(name.toString());
                    textSink.append("- ").append(name);
                    Object rating = item.get("rating");
                    if (rating != null) textSink.append("(评分 ").append(rating).append(")");
                    textSink.append("\n");
                }
            }
        } catch (Exception e) {
            log.warn("[Research] 解析检索结果失败: {}", e.getMessage());
        }
    }
}
