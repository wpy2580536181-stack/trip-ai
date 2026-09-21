package com.trip.backend.service.mcp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * 高德 MCP 子进程管理（对应 Python mcp/amap_process.py + amap_client.py 启动段）。
 *
 * ProcessBuilder spawn `npx -y @amap/amap-maps-mcp-server`，注入 AMAP_MAPS_API_KEY；
 * stdin/stdout 按行 JSON-RPC；可 terminate/isAlive。
 */
public class AmapProcess {

    private static final Logger log = LoggerFactory.getLogger(AmapProcess.class);

    private Process process;
    private OutputStream stdin;
    private BufferedReader stdout;
    private final String apiKey;
    private final String npxCmd;

    public AmapProcess(String apiKey, String npxCmd) {
        this.apiKey = apiKey;
        this.npxCmd = (npxCmd == null || npxCmd.isBlank()) ? "npx" : npxCmd;
    }

    /** 启动子进程（幂等）。 */
    public synchronized void start() throws IOException {
        if (process != null && process.isAlive()) {
            return;
        }
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("AMAP_MAPS_API_KEY not configured, cannot start Amap MCP server");
        }
        ProcessBuilder pb = new ProcessBuilder(
            npxCmd, "-y", "@amap/amap-maps-mcp-server");
        pb.environment().put("AMAP_MAPS_API_KEY", apiKey);
        pb.environment().put("AMAP_KEY", apiKey);
        pb.redirectErrorStream(false);
        log.info("starting amap mcp server: {} -y @amap/amap-maps-mcp-server", npxCmd);
        process = pb.start();
        stdin = process.getOutputStream();
        stdout = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));
    }

    /** 写一行 JSON-RPC 到 stdin。 */
    public void writeLine(String jsonLine) throws IOException {
        stdin.write(jsonLine.getBytes(StandardCharsets.UTF_8));
        stdin.flush();
    }

    /** 读一行 stdout（阻塞）。 */
    public String readLine() throws IOException {
        return stdout.readLine();
    }

    public synchronized boolean isAlive() {
        return process != null && process.isAlive();
    }

    public synchronized void terminate() {
        if (process != null && process.isAlive()) {
            process.destroy();
            try {
                process.waitFor(3, java.util.concurrent.TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            if (process.isAlive()) {
                process.destroyForcibly();
            }
            process = null;
        }
    }
}
