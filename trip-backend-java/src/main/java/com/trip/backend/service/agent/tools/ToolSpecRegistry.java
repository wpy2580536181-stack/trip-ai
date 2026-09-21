package com.trip.backend.service.agent.tools;

import com.trip.backend.service.llm.LlmClient;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 工具注册表（对应 Python bind_tools 集合）。
 *
 * - 注册全部业务工具（当前 7 个；J-D6 MCP 工具由 ToolLoader 动态并入）
 * - 每个工具按其韧性参数构造 ResilienceWrapper（超时/重试/熔断/fallback）
 * - call() 统一走 wrapper，工具失败永不抛给 LLM
 */
@Component
public class ToolSpecRegistry {

    private final Map<String, AgentTool> tools = new ConcurrentHashMap<>();
    private final Map<String, ResilienceWrapper> wrappers = new ConcurrentHashMap<>();

    public ToolSpecRegistry(List<AgentTool> businessTools) {
        // 3 个通勤工具（MCP 未接时无 Spring bean，手动实例化）
        List<AgentTool> all = new ArrayList<>(businessTools);
        all.add(new CommuteTools.ComputeOptimalCommute());
        all.add(new CommuteTools.SearchCommuteTips());
        all.add(new CommuteTools.SearchNearbyPois());

        for (AgentTool tool : all) {
            tools.put(tool.name(), tool);
            CircuitBreaker breaker = CircuitBreaker.getOrCreate(
                tool.name(), tool.circuitThreshold(), tool.circuitRecoverySec());
            wrappers.put(tool.name(), new ResilienceWrapper(
                tool.timeoutSec(), tool.retries(), tool.fallback(), breaker));
        }
    }

    /** 返回全部工具的 LLM 绑定 schema（对齐 Python bind_tools）。 */
    public List<LlmClient.ToolSpec> toolSpecs() {
        return tools.values().stream().map(AgentTool::spec).toList();
    }

    /** 工具总数（业务 + 通勤；MCP 工具由 J-D6 并入）。 */
    public int size() {
        return tools.size();
    }

    public AgentTool get(String name) {
        return tools.get(name);
    }

    /** 统一入口：走韧性包装执行工具。 */
    public String call(String name, Map<String, Object> args) {
        AgentTool tool = tools.get(name);
        ResilienceWrapper wrapper = wrappers.get(name);
        if (tool == null || wrapper == null) {
            return "{\"error\": \"unknown tool: " + name + "\"}";
        }
        return wrapper.call(() -> tool.execute(args));
    }
}
