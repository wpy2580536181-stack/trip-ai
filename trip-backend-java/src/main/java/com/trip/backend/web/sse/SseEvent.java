package com.trip.backend.web.sse;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * SSE 事件
 */
public class SseEvent {

    private final String id;        // 事件 ID（seq 或 null）
    private final String event;      // 事件类型（event name）
    private final String data;       // 事件数据（JSON 字符串）
    private final boolean isEnd;     // 是否终止事件

    private SseEvent(String id, String event, String data, boolean isEnd) {
        this.id = id;
        this.event = event;
        this.data = data;
        this.isEnd = isEnd;
    }

    public static SseEvent of(String id, String event, String data) {
        return new SseEvent(id, event, data, false);
    }

    public static SseEvent chunk(String id, String content) {
        return new SseEvent(id, "chunk", content, false);
    }

    public static SseEvent progress(String id, String stage, String status) {
        return new SseEvent(id, "progress", String.format("{\"type\":\"progress\",\"data\":{\"stage\":\"%s\",\"status\":\"%s\"}}", stage, status), false);
    }

    public static SseEvent complete(String id, String conversationId, Object usage) {
        String data = String.format("{\"type\":\"complete\",\"data\":{\"conversationId\":\"%s\",\"usage\":%s}", conversationId, toJson(usage));
        return new SseEvent(id, "complete", data, false);
    }

    public static SseEvent error(String id, String error) {
        return new SseEvent(id, "error", String.format("{\"type\":\"error\",\"error\":\"%s\"}", error), false);
    }

    public static SseEvent end() {
        return new SseEvent(null, null, null, true);
    }

    public String toSseFormat() {
        if (isEnd) {
            return "event: end\ndata: {\"done\": true}\n\n";
        }

        StringBuilder sb = new StringBuilder();
        if (id != null) {
            sb.append("id: ").append(id).append("\n");
        }
        if (event != null) {
            sb.append("event: ").append(event).append("\n");
        }
        sb.append("data: ").append(data).append("\n\n");
        return sb.toString();
    }

    private static String toJson(Object obj) {
        if (obj == null) return "null";
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(obj);
        } catch (Exception e) {
            return "{}";
        }
    }

    // Getters
    public String getId() { return id; }
    public String getEvent() { return event; }
    public String getData() { return data; }
    public boolean isEnd() { return isEnd; }
}
