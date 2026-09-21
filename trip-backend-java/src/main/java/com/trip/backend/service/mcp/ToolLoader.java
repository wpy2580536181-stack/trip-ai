package com.trip.backend.service.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.trip.backend.service.agent.tools.AgentTool;
import com.trip.backend.service.llm.LlmClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 高德 MCP 工具加载器（对应 Python mcp/tool_loader.py）。
 * 把 tools/list 返回的工具定义转成 AgentTool，调用走 AmapClient。
 */
public class ToolLoader {

    private final AmapClient amap;

    public ToolLoader(AmapClient amap) {
        this.amap = amap;
    }

    /** 加载 MCP 工具列表（调用失败返回空列表）。 */
    public List<AgentTool> loadTools() {
        List<AgentTool> out = new ArrayList<>();
        try {
            JsonNode result = amap.listTools();
            JsonNode tools = result.path("tools");
            if (!tools.isArray()) {
                return out;
            }
            for (JsonNode t : tools) {
                String name = t.path("name").asText("unknown_tool");
                String description = t.path("description").asText("");
                String inputSchema = t.has("inputSchema") ? t.get("inputSchema").toString() : "{}";
                out.add(new McpAgentTool(name, description, inputSchema));
            }
        } catch (Exception e) {
            return out;
        }
        return out;
    }

    /** 单个 MCP 工具的 AgentTool 适配。 */
    private class McpAgentTool implements AgentTool {
        private final String name;
        private final String description;
        private final String inputSchema;

        McpAgentTool(String name, String description, String inputSchema) {
            this.name = name;
            this.description = description;
            this.inputSchema = inputSchema;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public String description() {
            return description;
        }

        @Override
        public LlmClient.ToolSpec spec() {
            return new LlmClient.ToolSpec(name, description, inputSchema);
        }

        @Override
        public String execute(Map<String, Object> args) {
            return amap.callTool(name, args);
        }

        @Override
        public String fallback() {
            return "{\"error\": \"" + name + " 暂时不可用。\"}";
        }
    }
}
