package com.trip.backend.web.sse;

import jakarta.servlet.ServletOutputStream;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * SSE 写入器（对应 Python utils/stream.py SseWriter）
 * - 线程安全的事件队列
 * - 自动刷新
 * - 超时控制
 */
public class SseWriter {

    private final HttpServletResponse response;
    private final BlockingQueue<SseEvent> eventQueue;
    private final OutputStreamWriter writer;
    private final ServletOutputStream outputStream;

    // 流是否已关闭
    private volatile boolean closed = false;

    // 超时配置
    private static final long WRITE_TIMEOUT_MS = 30_000; // 30s

    public SseWriter(HttpServletResponse response) throws IOException {
        this.response = response;
        this.outputStream = response.getOutputStream();
        this.writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
        this.eventQueue = new LinkedBlockingQueue<>();

        // 设置 SSE 响应头
        response.setContentType("text/event-stream");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-cache");
        response.setHeader("Connection", "keep-alive");
        response.setHeader("X-Accel-Buffering", "no"); // Nginx 禁用缓冲
    }

    /**
     * 发送事件
     */
    public void send(SseEvent event) {
        if (closed) {
            return;
        }

        try {
            // 写入事件
            String sseFormat = event.toSseFormat();
            writer.write(sseFormat);
            writer.flush();
            outputStream.flush();

            // 如果是 end 事件，关闭流
            if (event.isEnd()) {
                close();
            }
        } catch (IOException e) {
            // 客户端断开连接
            close();
        }
    }

    /**
     * 发送事件（异步，不阻塞）
     */
    public void sendAsync(SseEvent event) {
        eventQueue.offer(event);
    }

    /**
     * 从队列消费事件（供后台线程调用）
     */
    public void drainEvents() {
        while (!closed && !eventQueue.isEmpty()) {
            try {
                SseEvent event = eventQueue.poll(100, TimeUnit.MILLISECONDS);
                if (event != null) {
                    send(event);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    /**
     * 关闭流
     */
    public void close() {
        if (!closed) {
            closed = true;
            try {
                writer.close();
                outputStream.close();
            } catch (IOException e) {
                // 忽略
            }
        }
    }

    /**
     * 检查是否已关闭
     */
    public boolean isClosed() {
        return closed;
    }

    /**
     * 发送心跳
     */
    public void sendHeartbeat() {
        send(SseEvent.of(null, "heartbeat", "{\"type\":\"heartbeat\"}"));
    }
}
