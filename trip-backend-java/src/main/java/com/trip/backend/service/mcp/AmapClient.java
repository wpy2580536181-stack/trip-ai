package com.trip.backend.service.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;

/**
 * 高德 MCP 业务客户端（对应 Python mcp/amap_client.py call_tool/list_tools）。
 * 调用走 Guards（熔断+限流+缓存+指标）。
 */
public class AmapClient {

    private final JsonRpcClient rpc;
    private final Guards guards;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AmapClient(JsonRpcClient rpc, Guards guards) {
        this.rpc = rpc;
        this.guards = guards;
    }

    /** 调用 MCP 工具，提取 content 文本拼接返回。 */
    public String callTool(String toolName, Map<String, Object> arguments) {
        String cacheKey = toolName + ":" + arguments;
        return guards.call(toolName, cacheKey, () -> {
            JsonNode result = rpc.send("tools/call", Map.of(
                "name", toolName,
                "arguments", arguments));
            return extractText(result);
        });
    }

    /** 列出可用工具。 */
    public JsonNode listTools() throws Exception {
        return rpc.send("tools/list", Map.of());
    }

    public Guards guards() {
        return guards;
    }

    private String extractText(JsonNode result) {
        JsonNode content = result.path("content");
        if (content.isArray()) {
            StringBuilder sb = new StringBuilder();
            for (JsonNode item : content) {
                if ("text".equals(item.path("type").asText()) && item.has("text")) {
                    if (sb.length() > 0) {
                        sb.append('\n');
                    }
                    sb.append(item.get("text").asText());
                }
            }
            return sb.toString();
        }
        return result.toString();
    }
}
