package com.trip.backend.service.chat;

import com.trip.backend.web.sse.SseEvent;
import com.trip.backend.web.sse.SseWriter;
import com.trip.backend.web.sse.StreamStore;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Chat 事件接收器（对应 Python utils/stream.py EventSink）
 *
 * 职责：
 * - 双写：SSE + StreamStore
 * - 发送 stream_meta 元数据
 * - 心跳检测（空闲 15s）
 */
@Component
public class EventSink {

    private final SseWriter sseWriter;
    private final StreamStore streamStore;

    // 追踪每条流的最后事件时间
    private final Map<String, Long> lastEventTimes = new ConcurrentHashMap<>();

    // 心跳间隔（毫秒）
    private static final long HEARTBEAT_INTERVAL_MS = 15_000;

    public EventSink(@Lazy SseWriter sseWriter, StreamStore streamStore) {
        this.sseWriter = sseWriter;
        this.streamStore = streamStore;
    }

    /**
     * 发送事件（双写）
     *
     * @param streamId 流 ID
     * @param eventType 事件类型
     * @param eventData 事件数据（JSON 字符串）
     */
    public void sendEvent(String streamId, String eventType, String eventData) {
        try {
            // 1. 写入 SSE
            sseWriter.send(SseEvent.of(streamId, eventType, eventData));

            // 2. 写入 StreamStore
            streamStore.appendEvent(streamId, eventType, eventData);

            // 3. 更新最后事件时间
            lastEventTimes.put(streamId, System.currentTimeMillis());

        } catch (Exception e) {
            // SSE 已关闭或写入失败，静默忽略
        }
    }

    /**
     * 发送 stream_meta 元数据（首事件）
     */
    public void sendStreamMeta(String streamId, String userId) {
        String meta = String.format(
            "{\"streamId\":\"%s\",\"userId\":\"%s\",\"type\":\"meta\"}",
            streamId, userId
        );
        sendEvent(streamId, "stream_meta", meta);
    }

    /**
     * 发送 chunk（LLM 增量内容）
     */
    public void sendChunk(String streamId, String content) {
        String data = String.format("{\"content\":%s}", escapeJson(content));
        sendEvent(streamId, "chunk", data);
    }

    /**
     * 发送 complete 事件（正常结束）
     */
    public void sendComplete(String streamId, Object usage) {
        String data = String.format("{\"usage\":%s}", toJson(usage));
        sendEvent(streamId, "complete", data);
        sendEnd(streamId);
    }

    /**
     * 发送 error 事件（异常结束）
     */
    public void sendError(String streamId, String error) {
        String data = String.format("{\"error\":%s}", escapeJson(error));
        sendEvent(streamId, "error", data);
        sendEnd(streamId);
    }

    /**
     * 发送 heartbeat 心跳
     */
    public void sendHeartbeat(String streamId) {
        sendEvent(streamId, "heartbeat", "{\"type\":\"heartbeat\"}");
    }

    /**
     * 发送 end 终止帧
     */
    private void sendEnd(String streamId) {
        try {
            sseWriter.send(SseEvent.end());
            streamStore.appendEvent(streamId, "end", "{}");
            lastEventTimes.remove(streamId);
        } catch (Exception e) {
            // 静默忽略
        }
    }

    /**
     * 检查流是否需要发送心跳（空闲超过 15s）
     */
    public boolean needsHeartbeat(String streamId) {
        Long lastTime = lastEventTimes.get(streamId);
        if (lastTime == null) {
            return false;
        }
        return (System.currentTimeMillis() - lastTime) >= HEARTBEAT_INTERVAL_MS;
    }

    /**
     * 清理流状态
     */
    public void cleanup(String streamId) {
        lastEventTimes.remove(streamId);
    }

    // ==================== JSON 辅助方法 ====================

    private static String escapeJson(String value) {
        if (value == null) {
            return "\"\"";
        }
        return "\"" + value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            + "\"";
    }

    private static String toJson(Object obj) {
        if (obj == null) {
            return "null";
        }
        // TODO: D8 阶段替换为 Jackson ObjectMapper
        return obj.toString();
    }
}
