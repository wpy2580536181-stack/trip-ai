package com.trip.backend.service.chat;

import com.trip.backend.web.sse.SseEvent;
import com.trip.backend.web.sse.SseWriter;
import com.trip.backend.web.sse.StreamStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;

import java.util.List;

import static org.mockito.Mockito.*;

/**
 * MessagePersistenceService 测试
 */
class MessagePersistenceServiceTest {

    @Mock
    private MessageRepository messageRepository;

    @Mock
    private ConversationRepository conversationRepository;

    private MessagePersistenceService service;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        service = new MessagePersistenceService(messageRepository, conversationRepository);
    }

    @Test
    void testPersistUserMessage() {
        // TODO: 实现
    }

    @Test
    void testCreateEmptyAssistantMessage() {
        // TODO: 实现
    }

    @Test
    void testAppendAssistantContent() {
        // TODO: 实现
    }

    @Test
    void testForceFlush() {
        // TODO: 实现
    }

    @Test
    void testTitleTruncation() {
        // TODO: 实现
    }
}
