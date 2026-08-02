package com.trip.backend.service.mcp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * MCP 工具加载器
 *
 * 对应 Python services/mcp/tool_loader.py
 *
 * 职责：
 * - 将 MCP tools/list 响应转换为工具定义
 * - MCP schema → ToolSpecRegistry.ToolSpec 动态转换
 */
public class ToolLoader {

    private static final Logger log = LoggerFactory.getLogger(ToolLoader.class);

    private final AmapClient amapClient;

    public ToolLoader(AmapClient amapClient) {
        this.amapClient = amapClient;
    }

    /**
     * 加载高德 MCP 工具列表
     *
     * @return 工具定义列表
     */
    public List<ToolSpecRegistry.ToolSpec> loadTools() {
        try {
            Map<String, Object> result = amapClient.listTools().get();

            List<Map<String, Object>> tools = (List<Map<String, Object>>) result.get("tools");
            if (tools == null || tools.isEmpty()) {
                log.warn("No tools returned from MCP server");
                return List.of();
            }

            List<ToolSpecRegistry.ToolSpec> specs = new ArrayList<>();
            for (Map<String, Object> tool : tools) {
                specs.add(convertMcpTool(tool));
            }

            log.info("Loaded {} Amap MCP tools", specs.size());
            return specs;

        } catch (Exception e) {
            log.error("Failed to load Amap MCP tools", e);
            return List.of();
        }
    }

    /**
     * 转换 MCP 工具定义为 ToolSpec
     */
    private ToolSpecRegistry.ToolSpec convertMcpTool(Map<String, Object> mcpTool) {
        String name = (String) mcpTool.get("name");
        String description = (String) mcpTool.get("description");

        Map<String, Object> inputSchema = (Map<String, Object>) mcpTool.get("inputSchema");
        Map<String, Object> parameters = convertSchema(inputSchema);

        return new ToolSpecRegistry.ToolSpec(
            name,
            description != null ? description : "",
            parameters
        );
    }

    /**
     * 转换 JSON Schema 为内部参数格式
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> convertSchema(Map<String, Object> schema) {
        if (schema == null) {
            return Map.of("type", "object", "properties", Map.of());
        }

        Map<String, Object> properties = (Map<String, Object>) schema.get("properties");
        if (properties == null) {
            properties = Map.of();
        }

        // 转换 required 列表
        List<String> required = (List<String>) schema.get("required");
        if (required == null) {
            required = List.of();
        }

        return Map.of(
            "type", schema.getOrDefault("type", "object"),
            "properties", properties,
            "required", required
        );
    }
}
