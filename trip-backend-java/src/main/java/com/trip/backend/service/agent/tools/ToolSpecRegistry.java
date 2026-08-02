package com.trip.backend.service.agent.tools;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 工具注册表
 *
 * 对应 Python tools/__init__.py 中的 bind_tools 逻辑
 *
 * 职责：
 * - 统一管理所有工具定义
 * - 导出工具列表（供 Agent 调用）
 * - 工具 Schema 序列化
 */
public class ToolSpecRegistry {

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

    private final List<ToolEntry> tools = new ArrayList<>();

    public ToolSpecRegistry() {
    }

    public void register(ToolEntry entry) {
        tools.add(entry);
    }

    /**
     * 获取所有工具列表
     */
    public List<ToolEntry> getAllTools() {
        return new ArrayList<>(tools);
    }

    /**
     * 根据名称查找工具
     */
    public ToolEntry findByName(String name) {
        return tools.stream()
            .filter(t -> t.name().equals(name))
            .findFirst()
            .orElse(null);
    }
}
