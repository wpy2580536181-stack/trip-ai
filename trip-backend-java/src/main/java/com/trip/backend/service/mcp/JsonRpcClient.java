package com.trip.backend.service.mcp;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * JSON-RPC 2.0 客户端（对应 Python mcp/amap_client.py _send_request）。
 *
 * - tools/list 握手轮询就绪（10×1s）
 * - 请求 id 递增
 * - tools/call 30s 超时
 */
public class JsonRpcClient {

    private static final int READY_RETRIES = 10;
    private static final long READY_RETRY_INTERVAL_MS = 1000;
    private static final long CALL_TIMEOUT_MS = 30_000;

    private final AmapProcess process;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final AtomicLong requestId = new AtomicLong(0);

    public JsonRpcClient(AmapProcess process) {
        this.process = process;
    }

    /** 启动并等待握手就绪；失败抛异常。 */
    public void startAndWaitReady() throws IOException, InterruptedException {
        process.start();
        for (int attempt = 0; attempt < READY_RETRIES; attempt++) {
            if (!process.isAlive()) {
                throw new IOException("高德 MCP server 进程已退出");
            }
            try {
                String probe = objectMapper.writeValueAsString(Map.of(
                    "jsonrpc", "2.0", "id", 0, "method", "tools/list", "params", Map.of())) + "\n";
                process.writeLine(probe);
                String line = process.readLine();
                if (line != null && !line.isBlank()) {
                    JsonNode resp = objectMapper.readTree(line);
                    if (resp.path("id").asInt(-1) == 0 && resp.has("result")) {
                        return; // ready
                    }
                }
            } catch (IOException e) {
                // 进程尚未就绪，继续轮询
            }
            Thread.sleep(READY_RETRY_INTERVAL_MS);
        }
        throw new IOException("高德 MCP server 启动超时（10s），未能完成 tools/list 握手");
    }

    /** 发送 JSON-RPC 请求并返回 result 节点（30s 超时读）。 */
    public JsonNode send(String method, Map<String, Object> params) throws Exception {
        long id = requestId.incrementAndGet();
        String request = objectMapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0", "id", id, "method", method, "params", params)) + "\n";
        process.writeLine(request);

        // 同步读响应（stdio 协议按行匹配 id；30s 超时）
        long deadline = System.currentTimeMillis() + CALL_TIMEOUT_MS;
        while (System.currentTimeMillis() < deadline) {
            String line = process.readLine();
            if (line == null) {
                throw new IOException("MCP server 未返回响应（EOF）");
            }
            if (line.isBlank()) {
                continue;
            }
            JsonNode resp = objectMapper.readTree(line);
            if (resp.path("id").asLong(-1) == id) {
                if (resp.has("error")) {
                    throw new IOException("MCP 错误: " + resp.path("error").path("message").asText("未知错误"));
                }
                return resp.path("result");
            }
            // 非本次响应（如通知），继续读
        }
        throw new IOException("MCP 请求超时（30s）: " + method);
    }

    public void close() {
        process.terminate();
    }
}
