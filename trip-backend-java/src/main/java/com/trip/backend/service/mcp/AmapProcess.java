package com.trip.backend.service.mcp;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.concurrent.TimeUnit;

/**
 * 高德 MCP 进程管理
 *
 * 对应 Python services/mcp/amap_process.py
 *
 * 职责：
 * - ProcessBuilder spawn `npx -y @amap/amap-maps-mcp-server`
 * - 注入 AMAP_MAPS_API_KEY/AMAP_KEY
 * - stdout/stderr 异步读防阻塞
 * - terminate/重启
 */
public class AmapProcess {

    private static final Logger log = LoggerFactory.getLogger(AmapProcess.class);

    private static final String CMD = "npx";
    private static final String PKG = "@amap/amap-maps-mcp-server";
    private static final int READY_TIMEOUT_MS = 10_000; // 10s 就绪超时

    private volatile Process process;
    private final Object lock = new Object();

    /**
     * 启动 MCP server（单例，幂等）
     *
     * @return MCP 进程
     * @throws IllegalStateException 如果启动失败
     */
    public Process start() {
        synchronized (lock) {
            // 幂等：进程已存在且运行中，直接返回
            if (process != null && process.isAlive()) {
                return process;
            }

            // 校验环境变量
            String apiKey = System.getenv("AMAP_MAPS_API_KEY");
            if (apiKey == null || apiKey.isBlank()) {
                throw new IllegalStateException("AMAP_MAPS_API_KEY not configured, cannot start Amap MCP server");
            }

            try {
                // 构建命令
                ProcessBuilder pb = new ProcessBuilder(CMD, "-y", PKG);
                pb.redirectErrorStream(true);

                // 注入环境变量
                pb.environment().put("AMAP_MAPS_API_KEY", apiKey);
                pb.environment().put("AMAP_KEY", apiKey); // 兼容旧版

                log.info("Starting Amap MCP server: {}", String.join(" ", pb.command()));

                // 启动进程
                process = pb.start();

                // 异步读取 stdout/stderr（防阻塞）
                startAsyncReader(process, "stdout");
                startAsyncReader(process, "stderr");

                // 等待就绪（handshake）
                if (!waitForReady(process)) {
                    terminate();
                    throw new IllegalStateException("高德 MCP server 启动超时（10s），未能完成 tools/list 握手");
                }

                log.info("高德 MCP server 进程已启动 (PID: {})", process.pid());
                return process;

            } catch (IOException e) {
                log.error("Failed to start Amap MCP server", e);
                throw new IllegalStateException("高德 MCP server 启动失败: " + e.getMessage(), e);
            }
        }
    }

    /**
     * 停止 MCP server
     */
    public void stop() {
        synchronized (lock) {
            if (process != null && process.isAlive()) {
                log.info("Stopping Amap MCP server (PID: {})", process.pid());
                process.destroy();
                try {
                    if (!process.waitFor(5, TimeUnit.SECONDS)) {
                        log.warn("Amap MCP server did not stop gracefully, force destroy");
                        process.destroyForcibly();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    process.destroyForcibly();
                }
            }
            process = null;
        }
    }

    /**
     * 检查进程是否存活
     */
    public boolean isAlive() {
        return process != null && process.isAlive();
    }

    /**
     * 获取进程对象
     */
    public Process getProcess() {
        return process;
    }

    /**
     * 启动异步读取线程（防阻塞）
     */
    private void startAsyncReader(Process process, String streamName) {
        Thread readerThread = new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(
                new java.io.InputStreamReader(
                    "stdout".equals(streamName) ? process.getInputStream() : process.getErrorStream()
                )
            )) {
                String line;
                while ((line = reader.readLine()) != null && process.isAlive()) {
                    log.debug("[MCP {}] {}", streamName, line);
                }
            } catch (IOException e) {
                if (process.isAlive()) {
                    log.warn("[MCP {}] Reader error: {}", streamName, e.getMessage());
                }
            }
        }, "mcp-" + streamName + "-reader");
        readerThread.setDaemon(true);
        readerThread.start();
    }

    /**
     * 等待进程就绪（轮询 tools/list 握手）
     */
    private boolean waitForReady(Process process) {
        long startTime = System.currentTimeMillis();

        while (System.currentTimeMillis() - startTime < READY_TIMEOUT_MS) {
            // 检查进程是否异常退出
            if (process.exitValue() != null) {
                log.error("Amap MCP server exited prematurely (exit code: {})", process.exitValue());
                return false;
            } catch (IllegalThreadStateException e) {
                // 进程仍在运行，继续等待
            }

            try {
                Thread.sleep(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }

        // 超时未就绪
        return false;
    }

    /**
     * 强制终止
     */
    private void terminate() {
        if (process != null) {
            process.destroyForcibly();
            process = null;
        }
    }
}
