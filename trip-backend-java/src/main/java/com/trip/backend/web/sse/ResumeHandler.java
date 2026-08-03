package com.trip.backend.web.sse;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;

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
     * 处理断点续传（带权限校验）
     *
     * @return ResumeResult
     * @throws ResumeException 400/403/404
     */
    public ResumeResult handleResumeWithAuth(String streamId, long lastSeq, String userId) throws ResumeException {
        // 获取 stream 状态（校验存在性）
        StreamStore.StreamState streamState;
        try {
            streamState = streamStore.getStreamState(streamId);
        } catch (StreamStore.StreamNotFoundException e) {
            throw new ResumeException(404, "Stream not found: " + streamId);
        }

        // 权限校验：owner 不匹配 → 403
        if (!streamState.userId().equals(userId)) {
            throw new ResumeException(403, "无权访问此 stream");
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
