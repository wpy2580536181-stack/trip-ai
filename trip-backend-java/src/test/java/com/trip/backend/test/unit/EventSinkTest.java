package com.trip.backend.test.unit;

import com.trip.backend.service.chat.EventSink;
import com.trip.backend.web.sse.SseEvent;
import com.trip.backend.web.sse.SseWriter;
import com.trip.backend.web.sse.StreamStore;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.atLeast;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class EventSinkTest {

    private final StreamStore streamStore = mock(StreamStore.class);
    private final SseWriter sseWriter = mock(SseWriter.class);
    private final EventSink eventSink = new EventSink(streamStore);

    @Test
    void sendStreamMetaWritesSseAndPersistsEvent() {
        eventSink.sendStreamMeta(sseWriter, "stream-1", "7");

        verify(sseWriter).send(any(SseEvent.class));
        verify(streamStore).appendEvent(eq("stream-1"), eq("stream_meta"), anyString());
    }

    @Test
    void sendCompleteWritesCompleteAndEndEvents() {
        eventSink.sendComplete(sseWriter, "stream-1", Map.of("total", 0));

        ArgumentCaptor<SseEvent> eventCaptor = ArgumentCaptor.forClass(SseEvent.class);
        verify(sseWriter, atLeast(2)).send(eventCaptor.capture());
        List<String> eventData = eventCaptor.getAllValues().stream()
            .map(SseEvent::getData)
            .filter(data -> data != null)
            .toList();
        assertTrue(eventData.contains("{\"usage\":{\"total\":0}}"), "complete 事件必须是合法 JSON");
        verify(streamStore).appendEvent(eq("stream-1"), eq("complete"), anyString());
        verify(streamStore).appendEvent(eq("stream-1"), eq("end"), eq("{}"));
    }
}
