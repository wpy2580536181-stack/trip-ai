package com.trip.backend.test.unit;

import com.trip.backend.service.chat.EventSink;
import com.trip.backend.web.sse.StreamStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.mock;

@SpringJUnitConfig(EventSinkWiringTest.TestConfig.class)
class EventSinkWiringTest {

    @Autowired
    private EventSink eventSink;

    @Test
    void contextCreatesEventSinkWithoutSseWriterBean() {
        assertNotNull(eventSink);
    }

    @Configuration
    @Import(EventSink.class)
    static class TestConfig {

        @Bean
        StreamStore streamStore() {
            return mock(StreamStore.class);
        }
    }
}
