package com.trip.backend.service.mcp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.concurrent.CompletableFuture;

/**
 * 高德 MCP 客户端门面
 *
 * 职责：
 * - callTool：调用工具
 * - listTools：列出可用工具
 * - 集成 guards（熔断器 + 限流器 + 缓存 + 指标）
 */
public class AmapClient {

    private static final Logger log = LoggerFactory.getLogger(AmapClient.class);

    private final JsonRpcClient rpcClient;
    private final MCPGuards guards;

    public AmapClient(AmapProcess amapProcess, MCPGuards guards) {
        this.rpcClient = new JsonRpcClient(amapProcess);
        this.guards = guards;

        // 等待就绪
        if (!rpcClient.waitForReady()) {
            throw new IllegalStateException("高德 MCP server 启动超时");
        }

        log.info("AmapClient initialized");
    }

    /**
     * 调用工具（带 guards）
     *
     * @param toolName 工具名
     * @param arguments 参数
     * @return 工具结果
     */
    public CompletableFuture<Map<String, Object>> callTool(String toolName, Map<String, Object> arguments) {
        long startTime = System.currentTimeMillis();

        return guards.executeWithGuards(toolName, () -> {
            CompletableFuture<Map<String, Object>> future = rpcClient.callTool(toolName, arguments);

            // 记录指标
            return future.whenComplete((result, error) -> {
                long durationMs = System.currentTimeMillis() - startTime;
                guards.recordMetrics(toolName, error == null, durationMs);
            });
        });
    }

    /**
     * 列出可用工具
     *
     * @return 工具列表
     */
    public CompletableFuture<Map<String, Object>> listTools() {
        return rpcClient.listTools();
    }

    /**
     * 关闭连接
     */
    public void close() {
        rpcClient.close();
    }
}
