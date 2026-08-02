package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import com.trip.backend.service.agent.tools.RetrieveKnowledgeTool;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * ToolSpecRegistry 工具注册表
 *
 * 职责：
 * - 统一管理所有工具定义
 * - 导出工具列表（供 Agent 调用）
 */
@Service
public class ToolSpecRegistry {

    private static final Logger log = LoggerFactory.getLogger(ToolSpecRegistry.class);

    public interface ToolSpec {
        String name();
        String description();
        Map<String, Object> parameters();
    }

    public record ToolEntry(String name, ToolSpec spec) {
        public Map<String, Object> toJson() {
            return Map.of(
                "name", name,
                "description", spec.description(),
                "parameters", spec.parameters()
            );
        }
    }

    private final java.util.List<ToolEntry> tools = new java.util.ArrayList<>();

    public void register(ToolEntry entry) {
        tools.add(entry);
        log.debug("[ToolSpecRegistry] Registered tool: {}", entry.name());
    }

    public List<ToolEntry> getAllTools() {
        return List.copyOf(tools);
    }

    public ToolEntry findByName(String name) {
        return tools.stream()
            .filter(t -> t.name().equals(name))
            .findFirst()
            .orElse(null);
    }
}
