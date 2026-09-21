package com.trip.backend.service.agent.tools;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.service.llm.LlmClient;
import com.trip.backend.service.rag.RetrievalPipeline;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * retrieve_knowledge 工具（对应 Python tools/retrieve_knowledge.py）。
 * 调用 J-C2/C3 检索管线，富化景点/美食/住宿/交通信息。
 */
@Component
public class RetrieveKnowledgeTool implements AgentTool {

    private static final Set<String> FOOD_KW =
        Set.of("美食", "好吃的", "餐厅", "吃", "饭", "早饭", "午饭", "晚饭", "早餐", "午餐", "晚餐");
    private static final Set<String> SPOT_KW = Set.of("景点", "好玩", "逛", "游览", "参观", "玩");

    private static final Map<String, String> CATEGORY_MAP = Map.of(
        "景点", "attraction",
        "美食", "food",
        "住宿", "hotel",
        "交通", "transportation"
    );

    private final RetrievalPipeline pipeline;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public RetrieveKnowledgeTool(RetrievalPipeline pipeline) {
        this.pipeline = pipeline;
    }

    @Override
    public String name() {
        return "retrieve_knowledge";
    }

    @Override
    public String description() {
        return """
            从旅行知识库检索景点、美食、住宿、交通等真实信息。

            当用户询问某个城市具体的景点推荐、美食、交通、住宿时，必须调用此工具获取真实数据。""";
    }

    @Override
    public LlmClient.ToolSpec spec() {
        return new LlmClient.ToolSpec(name(), description(),
            """
            {"type":"object",
             "properties":{
               "query":{"type":"string","description":"搜索关键词，描述你想了解的景点主题"},
               "city":{"type":"string","description":"目标城市名"},
               "category":{"type":"string","description":"景点类型：景点/美食/住宿/交通"}
             },
             "required":["query","city"]}""");
    }

    @Override
    public String execute(Map<String, Object> args) throws Exception {
        String query = str(args.get("query"));
        String city = str(args.get("city"));
        String category = strOrNull(args.get("category"));

        // 中文分类归一化；未传则按关键词推断（对齐 Python）
        if (category == null || category.isBlank()) {
            String q = query == null ? "" : query;
            if (FOOD_KW.stream().anyMatch(q::contains)) {
                category = "美食";
            } else if (SPOT_KW.stream().anyMatch(q::contains)) {
                category = "景点";
            }
        }
        String dbCategory = category == null ? null : CATEGORY_MAP.getOrDefault(category, category);
        String searchCategory = (dbCategory == null || dbCategory.isBlank()) ? "attraction" : dbCategory;

        List<Map<String, Object>> results = pipeline.retrieve(query, city, searchCategory, 5);
        if (results == null || results.isEmpty()) {
            return "知识库中没有找到 " + city + " 的相关信息。";
        }
        return objectMapper.writeValueAsString(results);
    }

    @Override
    public String fallback() {
        return "知识库暂时不可用，请基于通用旅行知识回答。";
    }

    @Override
    public long timeoutSec() {
        return 8;
    }

    @Override
    public int retries() {
        return 0;
    }

    private static String str(Object v) {
        return v == null ? "" : v.toString().trim();
    }

    private static String strOrNull(Object v) {
        String s = str(v);
        return s.isEmpty() ? null : s;
    }
}
