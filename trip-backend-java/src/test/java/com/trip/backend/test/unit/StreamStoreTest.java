package com.trip.backend.test.unit;

import com.trip.backend.web.sse.StreamStore;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class StreamStoreTest {

    @Test
    void memoryFallbackEvictsOldestStreamWhenFull() {
        StreamStore streamStore = memoryFallbackStore();

        StreamStore.StreamState first = streamStore.createStream("user-1", "conv-1");
        StreamStore.StreamState latest = null;
        for (int i = 1; i <= 128; i++) {
            latest = streamStore.createStream("user-" + i, "conv-" + i);
        }

        assertThrows(
            StreamStore.StreamNotFoundException.class,
            () -> streamStore.getStreamState(first.streamId())
        );
        assertNotNull(streamStore.getStreamState(latest.streamId()));
    }

    @Test
    void memoryFallbackKeepsEventsForActiveStream() {
        StreamStore streamStore = memoryFallbackStore();
        StreamStore.StreamState state = streamStore.createStream("user-1", "conv-1");

        long seq = streamStore.appendEvent(state.streamId(), "chunk", "{\"content\":\"hi\"}");
        var events = streamStore.getEventsSince(state.streamId(), seq - 1);

        assertNotNull(events);
        org.junit.jupiter.api.Assertions.assertEquals(1, events.size());
        org.junit.jupiter.api.Assertions.assertEquals("chunk", events.get(0).type());
    }

    private StreamStore memoryFallbackStore() {
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        ValueOperations<String, String> valueOps = mock(ValueOperations.class);
        when(redisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("health-check"))
            .thenThrow(new IllegalStateException("redis unavailable"));
        return new StreamStore(redisTemplate);
    }
}
