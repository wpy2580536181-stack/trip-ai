package com.trip.backend.test.unit;

import com.trip.backend.domain.entity.TokenUsageLog;
import com.trip.backend.domain.repository.TokenUsageLogRepository;
import com.trip.backend.middleware.TokenBudgetManager;
import com.trip.backend.middleware.TokenMonitor;
import com.trip.backend.middleware.TokenTrackingCallback;
import dev.langchain4j.model.output.TokenUsage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

class TokenTrackingCallbackTest {

    private final TokenUsageLogRepository repository = mock(TokenUsageLogRepository.class);
    private final TokenTrackingCallback callback = new TokenTrackingCallback(
        new TokenMonitor(10),
        new TokenBudgetManager(1_000_000, 1, 1_000_000, 1),
        repository
    );

    @AfterEach
    void clearContext() {
        callback.clearContext();
    }

    @Test
    void recordLlmUsagePersistsTokenUsageLogAsynchronously() {
        callback.setContext(7L, "chat", "/api/trip/chat");

        callback.recordLlmUsage(new TokenUsage(10, 20, 30), 123L);

        ArgumentCaptor<TokenUsageLog> captor = ArgumentCaptor.forClass(TokenUsageLog.class);
        verify(repository, timeout(2000)).save(captor.capture());

        TokenUsageLog saved = captor.getValue();
        assertEquals(7L, saved.getUserId());
        assertEquals("chat", saved.getRequestType());
        assertEquals("/api/trip/chat", saved.getRoute());
        assertEquals(10, saved.getPromptTokens());
        assertEquals(20, saved.getCompletionTokens());
        assertEquals(30, saved.getTotalTokens());
        assertEquals(123, saved.getLatencyMs());
    }
}
