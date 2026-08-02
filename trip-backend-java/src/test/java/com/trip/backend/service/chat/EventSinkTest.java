package com.trip.backend.service.chat;

import com.trip.backend.web.sse.SseEvent;
import com.trip.backend.web.sse.SseWriter;
import com.trip.backend.web.sse.StreamStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import static org.mockito.Mockito.*;

/**
 * EventSink 单元测试
 */
class EventSinkTest {

    @Mock
    private SseWriter sseWriter;

    @Mock
    private StreamStore streamStore;

    private EventSink eventSink;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        eventSink = new EventSink(sseWriter, streamStore);
    }

    @Test
    void testSendEvent() {
        // Arrange
        String streamId = "test-stream";
        String eventType = "chunk";
        String eventData = "{\"content\":\"hello\"}";

        // Act
        eventSink.sendEvent(streamId, eventType, eventData);

        // Assert
        verify(sseWriter, times(1)).send(any(SseEvent.class));
        verify(streamStore, times(1)).appendEvent(eq(streamId), eq(eventType), eq(eventData));
    }

    @Test
    void testSendStreamMeta() {
        // Arrange
        String streamId = "test-stream";
        String userId = "123";

        // Act
        eventSink.sendStreamMeta(streamId, userId);

        // Assert
        verify(sseWriter, times(1)).send(any(SseEvent.class));
        verify(streamStore, times(1)).appendEvent(eq(streamId), eq("stream_meta"), anyString());
    }

    @Test
    void testSendComplete() {
        // Arrange
        String streamId = "test-stream";
        Object usage = Map.of("prompt", 10, "completion", 20, "total", 30, "cached", 0);

        // Act
        eventSink.sendComplete(streamId, usage);

        // Assert
        verify(sseWriter, times(2)).send(any(SseEvent.class)); // complete + end
        verify(streamStore, times(2)).appendEvent(anyString(), anyString(), anyString());
    }

    @Test
    void testSendError() {
        // Arrange
        String streamId = "test-stream";
        String error = "test error";

        // Act
        eventSink.sendError(streamId, error);

        // Assert
        verify(sseWriter, times(2)).send(any(SseEvent.class)); // error + end
        verify(streamStore, times(2)).appendEvent(anyString(), anyString(), anyString());
    }

    @Test
    void testSendHeartbeat() {
        // Arrange
        String streamId = "test-stream";

        // Act
        eventSink.sendHeartbeat(streamId);

        // Assert
        verify(sseWriter, times(1)).send(any(SseEvent.class));
        verify(streamStore, times(1)).appendEvent(eq(streamId), eq("heartbeat"), anyString());
    }

    @Test
    void testNeedsHeartbeat() {
        // Arrange
        String streamId = "test-stream";
        eventSink.sendChunk(streamId, "test");

        // Act & Assert - 刚发送完事件，不应该需要心跳
        assert !eventSink.needsHeartbeat(streamId);

        // 模拟 16s 后
        // 注意：这里无法直接测试时间，需要依赖集成测试
    }

    @Test
    void testCleanup() {
        // Arrange
        String streamId = "test-stream";
        eventSink.sendChunk(streamId, "test");

        // Act
        eventSink.cleanup(streamId);

        // Assert
        assert !eventSink.needsHeartbeat(streamId);
    }
}
