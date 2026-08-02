package com.trip.backend.service.mcp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.*;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

/**
 * JSON-RPC 2.0 客户端
 *
 * 对应 Python services/mcp/amap_client.py::_send_request
 *
 * 职责：
 * - tools/list 握手探测
 * - tools/call 调用（30s 超时）
 * - ID 递增
 * - 错误提取
 */
public class JsonRpcClient {

    private static final Logger log = LoggerFactory.getLogger(JsonRpcClient.class);

    private static final int TIMEOUT_SEC = 30;
    private static final int READY_PROBE_TIMEOUT_MS = 1000;

    private final AmapProcess amapProcess;
    private final Process process;

    // 请求 ID 计数器
    private int nextRequestId = 1;

    public JsonRpcClient(AmapProcess amapProcess) {
        this.amapProcess = amapProcess;
        this.process = amapProcess.start();
    }

    /**
     * 发送 JSON-RPC 请求
     *
     * @param method RPC 方法名
     * @param params 参数
     * @return 响应结果
     * @throws IOException 如果通信失败
     */
    public CompletableFuture<Map<String, Object>> sendRequest(String method, Map<String, Object> params) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                // 1. 构建请求
                int requestId = nextRequestId++;
                Map<String, Object> request = Map.of(
                    "jsonrpc", "2.0",
                    "id", requestId,
                    "method", method,
                    "params", params != null ? params : Map.of()
                );

                String jsonRequest = toJson(request) + "\n";

                // 2. 发送到 stdin
                OutputStream stdin = process.getOutputStream();
                stdin.write(jsonRequest.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                stdin.flush();

                log.debug("[JsonRpcClient] Sent request: {}", method);

                // 3. 读取响应（阻塞等待）
                BufferedReader stdout = new BufferedReader(
                    new InputStreamReader(process.getInputStream(), java.nio.charset.StandardCharsets.UTF_8)
                );

                long startTime = System.currentTimeMillis();
                String line;
                while (true) {
                    // 超时检查
                    if (System.currentTimeMillis() - startTime > TIMEOUT_SEC * 1000) {
                        throw new IOException("MCP request timeout after " + TIMEOUT_SEC + "s");
                    }

                    // 检查进程是否存活
                    if (!process.isAlive()) {
                        throw new IOException("MCP server process died");
                    }

                    line = stdout.readLine();
                    if (line == null) {
                        throw new EOFException("MCP server closed connection");
                    }

                    if (line.isBlank()) {
                        continue;
                    }

                    // 解析响应
                    try {
                        Map<String, Object> response = fromJson(line);

                        // 检查是否是对应请求的响应
                        Object id = response.get("id");
                        if (id instanceof Number && ((Number) id).intValue() == requestId) {
                            // 检查错误
                            if (response.containsKey("error")) {
                                Map<String, Object> error = (Map<String, Object>) response.get("error");
                                throw new IOException("MCP error: " + error.get("message"));
                            }

                            log.debug("[JsonRpcClient] Received response for: {}", method);
                            return (Map<String, Object>) response.get("result");
                        }

                    } catch (Exception e) {
                        log.warn("[JsonRpcClient] Failed to parse response: {}", line, e);
                    }
                }

            } catch (Exception e) {
                log.error("[JsonRpcClient] Request failed: {}", method, e);
                throw new IOException("MCP request failed: " + e.getMessage(), e);
            }
        });
    }

    /**
     * tools/list 握手探测
     *
     * @return 工具列表
     */
    public CompletableFuture<Map<String, Object>> listTools() {
        return sendRequest("tools/list", Map.of());
    }

    /**
     * tools/call 调用工具
     *
     * @param toolName 工具名
     * @param arguments 参数
     * @return 工具结果
     */
    public CompletableFuture<Map<String, Object>> callTool(String toolName, Map<String, Object> arguments) {
        return sendRequest("tools/call", Map.of(
            "name", toolName,
            "arguments", arguments
        ));
    }

    /**
     * 等待 server 就绪（10×1s 轮询）
     *
     * @return true 如果就绪
     */
    public boolean waitForReady() {
        for (int i = 0; i < 10; i++) {
            try {
                CompletableFuture<Map<String, Object>> future = listTools();
                Map<String, Object> result = future.get(READY_PROBE_TIMEOUT_MS, TimeUnit.MILLISECONDS);
                if (result != null) {
                    log.info("Amap MCP server ready (attempt {})", i + 1);
                    return true;
                }
            } catch (Exception e) {
                log.debug("Amap MCP not ready yet (attempt {}/10): {}", i + 1, e.getMessage());
            }

            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }

    /**
     * 关闭连接
     */
    public void close() {
        amapProcess.stop();
    }

    // ==================== JSON 工具方法 ====================

    private static String toJson(Object obj) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize JSON", e);
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> fromJson(String json) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper()
                .readValue(json, Map.class);
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse JSON: " + json, e);
        }
    }
}
