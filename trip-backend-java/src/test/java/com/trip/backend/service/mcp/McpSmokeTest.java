package com.trip.backend.service.mcp;

import org.junit.jupiter.api.Test;
import org.opentest4j.TestAbortedException;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D6 判定 1：MCP smoke test（启动→就绪→调用成功）。
 *
 * 需要真实环境：
 *  - 已配置 AMAP_MAPS_API_KEY 环境变量
 *  - 本机有 npx（Node.js）
 * 任一不满足 → TestAbortedException 跳过，不影响 CI。
 */
class McpSmokeTest {

    @Test
    void startReadyAndCall() throws Exception {
        String apiKey = System.getenv("AMAP_MAPS_API_KEY");
        if (apiKey == null || apiKey.isBlank()) {
            throw new TestAbortedException("未配置 AMAP_MAPS_API_KEY，跳过 MCP smoke test");
        }
        try {
            new ProcessBuilder("npx", "--version").start().waitFor(5, java.util.concurrent.TimeUnit.SECONDS);
        } catch (Exception e) {
            throw new TestAbortedException("无 npx/Node.js，跳过 MCP smoke test");
        }

        AmapProcess process = new AmapProcess(apiKey, "npx");
        JsonRpcClient rpc = new JsonRpcClient(process);
        try {
            // 启动 + tools/list 握手（10×1s 轮询）
            rpc.startAndWaitReady();
            // 调用一次 tools/list 验证就绪后可用
            var tools = rpc.send("tools/list", java.util.Map.of());
            assertTrue(tools != null, "tools/list 应返回结果");
        } finally {
            rpc.close();
        }
    }
}
