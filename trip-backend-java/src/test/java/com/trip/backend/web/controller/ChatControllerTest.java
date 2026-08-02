package com.trip.backend.web.controller;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.service.TripService;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.chat.MessagePersistenceService;
import com.trip.backend.service.chat.NonTravelShortCircuit;
import com.trip.backend.web.sse.ResumeHandler;
import com.trip.backend.web.sse.StreamStore;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ChatController 集成测试
 */
@SpringBootTest
class ChatControllerTest {

    @Autowired
    private ChatController chatController;

    @Test
    void testNonTravelShortCircuit() {
        // TODO: 实现
    }

    @Test
    void testChatStream() {
        // TODO: 实现
    }
}
