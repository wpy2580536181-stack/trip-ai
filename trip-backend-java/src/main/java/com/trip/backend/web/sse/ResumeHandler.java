package com.trip.backend.web.sse;

import jakarta.servlet.http.HttpServletRequest;

/**
 * 断点续传处理器（对应 Python streamable-agent-resumable.md）
 * - X-Stream-Id + Last-Event-ID 同时存在才触发
 * - 重发 seq > lastSeq 全部事件（保留原 id）
 * - 只读重放不改状态
 */
public class ResumeHandler {

    private final StreamStore streamStore;

    public ResumeHandler(StreamStore streamStore) {
        this.streamStore = streamStore;
    }

    /**
     * 检查是否启用断点续传
     */
    public boolean isResumeEnabled(HttpServletRequest request) {
        String streamId = request.getHeader("X-Stream-Id");
        String lastEventId = request.getHeader("Last-Event-ID");

        return streamId != null && !streamId.isBlank()
            && lastEventId != null && !lastEventId.isBlank();
    }

    /**
     * 处理断点续传
     *
     * @return ResumeResult（null 表示非续传请求）
     */
    public ResumeResult handleResume(HttpServletRequest request) throws ResumeException {
        String streamId = request.getHeader("X-Stream-Id");
        String lastEventId = request.getHeader("Last-Event-ID");

        if (streamId == null || lastEventId == null) {
            return null; // 非续传请求
        }

        // 解析 lastSeq
        long lastSeq;
        try {
            lastSeq = Long.parseLong(lastEventId);
            if (lastSeq < 0) {
                throw new IllegalArgumentException("Last-Event-ID must be non-negative");
            }
        } catch (NumberFormatException e) {
            throw new ResumeException(400, "Invalid Last-Event-ID: " + lastEventId);
        }

        // 获取 stream 状态
        StreamStore.StreamState streamState;
        try {
            streamState = streamStore.getStreamState(streamId);
        } catch (StreamStore.StreamNotFoundException e) {
            throw new ResumeException(404, "Stream not found: " + streamId);
        }

        // 获取事件
        try {
            List<StreamStore.StreamEvent> events = streamStore.getEventsSince(streamId, lastSeq);
            return new ResumeResult(streamId, events, streamState.totalSeq());
        } catch (IllegalArgumentException e) {
            if ("lastSeq > totalSeq".equals(e.getMessage())) {
                throw new ResumeException(400, "lastSeq > totalSeq");
            }
            throw new ResumeException(400, "Invalid Last-Event-ID", e);
        }
    }

    public record ResumeResult(String streamId, List<StreamStore.StreamEvent> events, long totalSeq) {}

    public static class ResumeException extends RuntimeException {
        public final int statusCode;

        public ResumeException(int statusCode, String message) {
            super(message);
            this.statusCode = statusCode;
        }

        public ResumeException(int statusCode, String message, Throwable cause) {
            super(message, cause);
            this.statusCode = statusCode;
        }
    }
}
