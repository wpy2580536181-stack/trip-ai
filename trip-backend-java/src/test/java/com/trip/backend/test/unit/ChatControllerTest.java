package com.trip.backend.test.unit;

import com.trip.backend.domain.dto.ChatRequest;
import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.infra.metrics.PrometheusMetrics;
import com.trip.backend.service.ConversationService;
import com.trip.backend.service.TripService;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.chat.MessagePersistenceService;
import com.trip.backend.service.chat.NonTravelShortCircuit;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.controller.ChatController;
import com.trip.backend.web.sse.StreamStore;
import com.trip.backend.web.sse.SseWriter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.ServletOutputStream;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ChatControllerTest {

    private final TripService tripService = mock(TripService.class);
    private final EventSink eventSink = mock(EventSink.class);
    private final MessagePersistenceService messagePersistenceService = mock(MessagePersistenceService.class);
    private final NonTravelShortCircuit nonTravelShortCircuit = mock(NonTravelShortCircuit.class);
    private final StreamStore streamStore = mock(StreamStore.class);
    private final ConversationService conversationService = mock(ConversationService.class);
    private final PrometheusMetrics prometheusMetrics = mock(PrometheusMetrics.class);
    private final com.trip.backend.service.llm.LlmGateway llmGateway = mock(com.trip.backend.service.llm.LlmGateway.class);

    private final ChatController controller = new ChatController(
        tripService,
        eventSink,
        messagePersistenceService,
        nonTravelShortCircuit,
        streamStore,
        conversationService,
        prometheusMetrics,
        llmGateway
    );

    @Test
    void rejectsConversationNotOwnedByUser() {
        Long userId = 1L;
        Long conversationId = 99L;
        when(conversationService.findByIdAndUserId(conversationId, userId)).thenReturn(Optional.empty());

        ChatRequest request = new ChatRequest("去成都玩三天", conversationId, null);
        AppException exception = assertThrows(
            AppException.class,
            () -> controller.chat(mock(HttpServletRequest.class), request, userId, mock(HttpServletResponse.class))
        );

        assertEquals(404, exception.getStatusCode());
        verify(eventSink, never()).sendStreamMeta(any(SseWriter.class), any(), any());
    }

    @Test
    void shortCircuitPersistsAssistantMessageInOwnedConversation() throws Exception {
        Long userId = 1L;
        Long conversationId = 42L;
        Conversation conversation = new Conversation();
        conversation.setId(conversationId);
        conversation.setUserId(userId);
        when(conversationService.findByIdAndUserId(conversationId, userId))
            .thenReturn(Optional.of(conversation));

        Message userMessage = new Message();
        userMessage.setId(10L);
        Message assistantMessage = new Message();
        assistantMessage.setId(11L);

        when(streamStore.createStream(String.valueOf(userId), String.valueOf(conversationId)))
            .thenReturn(new StreamStore.StreamState("stream-1", String.valueOf(userId), 0));
        when(messagePersistenceService.persistUserMessage(userId, conversationId, "这不是旅行问题"))
            .thenReturn(userMessage);
        when(nonTravelShortCircuit.isNonTravel("这不是旅行问题")).thenReturn(true);
        when(messagePersistenceService.createEmptyAssistantMessage(userId, conversationId))
            .thenReturn(assistantMessage);

        HttpServletResponse response = mock(HttpServletResponse.class);
        when(response.getOutputStream()).thenReturn(mock(ServletOutputStream.class));

        ChatRequest request = new ChatRequest("这不是旅行问题", conversationId, null);
        controller.chat(mock(HttpServletRequest.class), request, userId, response);

        verify(messagePersistenceService).createEmptyAssistantMessage(userId, conversationId);
        verify(messagePersistenceService).appendAssistantContent(assistantMessage.getId(), "这是一个非旅行相关的问题，我目前只能帮您规划旅行行程。请问有什么关于旅行的问题我可以帮您？");
    }
}
