package com.trip.backend.test.unit;

import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Feedback;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.repository.ConversationRepository;
import com.trip.backend.domain.repository.FeedbackRepository;
import com.trip.backend.domain.repository.MessageRepository;
import com.trip.backend.service.FeedbackService;
import com.trip.backend.utils.AppException;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class FeedbackServiceTest {

    private final FeedbackRepository feedbackRepository = mock(FeedbackRepository.class);
    private final MessageRepository messageRepository = mock(MessageRepository.class);
    private final ConversationRepository conversationRepository = mock(ConversationRepository.class);
    private final FeedbackService feedbackService = new FeedbackService(
        feedbackRepository,
        messageRepository,
        conversationRepository
    );

    @Test
    void rejectsRatingOutsideAllowedValues() {
        AppException exception = assertThrows(
            AppException.class,
            () -> feedbackService.submitFeedback(1L, 2L, 3L, 5, "good", null)
        );

        assertEquals(400, exception.getStatusCode());
        verify(feedbackRepository, never()).save(any());
    }

    @Test
    void rejectsFeedbackForMessageInAnotherUsersConversation() {
        Message message = new Message();
        message.setId(2L);
        message.setConversationId(3L);
        when(messageRepository.findById(2L)).thenReturn(Optional.of(message));
        when(conversationRepository.findByIdAndUserId(3L, 1L)).thenReturn(Optional.empty());

        AppException exception = assertThrows(
            AppException.class,
            () -> feedbackService.submitFeedback(1L, 2L, 3L, 1, "good", null)
        );

        assertEquals(404, exception.getStatusCode());
        verify(feedbackRepository, never()).save(any());
    }

    @Test
    void storesConversationIdForNewFeedback() {
        Long userId = 1L;
        Long messageId = 2L;
        Long conversationId = 3L;
        Message message = new Message();
        message.setId(messageId);
        message.setConversationId(conversationId);
        Conversation conversation = new Conversation();
        conversation.setId(conversationId);
        conversation.setUserId(userId);

        when(messageRepository.findById(messageId)).thenReturn(Optional.of(message));
        when(conversationRepository.findByIdAndUserId(conversationId, userId))
            .thenReturn(Optional.of(conversation));
        when(feedbackRepository.findByUserIdAndMessageId(userId, messageId)).thenReturn(Optional.empty());
        when(feedbackRepository.save(any(Feedback.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Feedback saved = feedbackService.submitFeedback(userId, messageId, conversationId, -1, "bad", null);

        assertEquals(conversationId, saved.getConversationId());
        assertEquals(-1, saved.getRating());
        verify(feedbackRepository).save(saved);
    }
}
