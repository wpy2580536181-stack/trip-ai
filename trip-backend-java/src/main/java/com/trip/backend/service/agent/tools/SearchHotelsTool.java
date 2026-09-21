package com.trip.backend.service.agent.tools;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.service.llm.LlmClient;
import com.trip.backend.service.rag.RetrievalPipeline;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * search_hotels 工具（对应 Python tools/search_hotels.py）。
 */
@Component
public class SearchHotelsTool implements AgentTool {

    private final RetrievalPipeline pipeline;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SearchHotelsTool(RetrievalPipeline pipeline) {
        this.pipeline = pipeline;
    }

    @Override
    public String name() {
        return "search_hotels";
    }

    @Override
    public String description() {
        return """
            查询目标城市的住宿信息。

            当用户询问住宿、酒店、旅馆、民宿时使用。""";
    }

    @Override
    public LlmClient.ToolSpec spec() {
        return new LlmClient.ToolSpec(name(), description(),
            """
            {"type":"object",
             "properties":{
               "city":{"type":"string","description":"目标城市名"},
               "budget":{"type":"number","description":"预算上限（元/晚）"},
               "level":{"type":"string","description":"住宿档次：economy/comfort/luxury"}
             },
             "required":["city"]}""");
    }

    @Override
    public String execute(Map<String, Object> args) throws Exception {
        String city = args.get("city") == null ? "" : args.get("city").toString().trim();
        String budget = args.get("budget") == null ? null : args.get("budget").toString();
        String level = args.get("level") == null ? null : args.get("level").toString().trim();

        StringBuilder query = new StringBuilder();
        if (level != null && !level.isBlank()) {
            query.append(level).append(' ');
        }
        query.append(city).append(" 住宿酒店");

        List<Map<String, Object>> results = pipeline.retrieve(query.toString(), city, "hotel", 5);
        if (results == null || results.isEmpty()) {
            String budgetStr = budget != null ? "，预算 " + budget + " 元/晚" : "";
            return "知识库中暂无 " + city + " 的住宿数据" + budgetStr + "。请基于通用知识推荐。";
        }
        return objectMapper.writeValueAsString(results);
    }

    @Override
    public String fallback() {
        return "住宿信息暂时不可用，请基于通用旅行知识回答。";
    }

    @Override
    public int retries() {
        return 1;
    }
}
