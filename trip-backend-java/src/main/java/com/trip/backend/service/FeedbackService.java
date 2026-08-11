package com.trip.backend.service;

import com.trip.backend.domain.entity.Feedback;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.repository.ConversationRepository;
import com.trip.backend.domain.repository.FeedbackRepository;
import com.trip.backend.domain.repository.MessageRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Feedback service（简化版）
 */
@Service
public class FeedbackService {

    private final FeedbackRepository feedbackRepository;
    private final MessageRepository messageRepository;
    private final ConversationRepository conversationRepository;

    public FeedbackService(FeedbackRepository feedbackRepository,
                           MessageRepository messageRepository,
                           ConversationRepository conversationRepository) {
        this.feedbackRepository = feedbackRepository;
        this.messageRepository = messageRepository;
        this.conversationRepository = conversationRepository;
    }

    /**
     * 获取用户反馈列表
     */
    @Transactional(readOnly = true)
    public Page<Feedback> getUserFeedbacks(Long userId, int page, int pageSize) {
        return feedbackRepository.findByUserIdOrderByCreatedAtDesc(
            userId,
            PageRequest.of(page - 1, pageSize)
        );
    }

    /**
     * 提交反馈
     */
    @Transactional
    public Feedback submitFeedback(Long userId, Long messageId, Long conversationId, Integer rating,
                                   String comment, List<String> tags) {
        if (rating == null || !Set.of(1, -1).contains(rating)) {
            throw AppException.badRequest("rating 仅支持 1 或 -1");
        }
        if (messageId == null) {
            throw AppException.badRequest("messageId 不能为空");
        }
        if (conversationId == null) {
            throw AppException.badRequest("conversationId 不能为空");
        }

        Message message = messageRepository.findById(messageId)
            .orElseThrow(() -> AppException.notFound("消息不存在"));
        if (!conversationId.equals(message.getConversationId())
            || conversationRepository.findByIdAndUserId(conversationId, userId).isEmpty()) {
            throw AppException.notFound("消息不存在");
        }

        return feedbackRepository.findByUserIdAndMessageId(userId, messageId)
            .map(existing -> {
                existing.setRating(rating);
                existing.setConversationId(conversationId);
                existing.setComment(comment);
                existing.setTags(tags);
                return existing;
            })
            .orElseGet(() -> {
                Feedback feedback = new Feedback(userId, messageId, rating);
                feedback.setConversationId(conversationId);
                feedback.setComment(comment);
                feedback.setTags(tags);
                return feedbackRepository.save(feedback);
            });
    }

    /**
     * 获取消息反馈统计
     */
    @Transactional(readOnly = true)
    public Map<String, Object> getMessageStats(Long messageId) {
        Object[] stats = feedbackRepository.getStatsByMessageId(messageId);

        Long up = stats[0] != null ? ((Number) stats[0]).longValue() : 0L;
        Long down = stats[1] != null ? ((Number) stats[1]).longValue() : 0L;
        Long total = stats[2] != null ? ((Number) stats[2]).longValue() : 0L;

        Double satisfactionRate = total > 0 ? (double) up / total * 100 : null;

        Map<String, Object> result = new HashMap<>();
        result.put("up", up);
        result.put("down", down);
        result.put("total", total);
        result.put("satisfactionRate", satisfactionRate);

        return result;
    }

    /**
     * 获取全局统计
     */
    @Transactional(readOnly = true)
    public Map<String, Object> getGlobalStats(int days) {
        Object[] stats = feedbackRepository.getGlobalStats(
            java.time.OffsetDateTime.now().minusDays(days)
        );

        Long total = stats[0] != null ? ((Number) stats[0]).longValue() : 0L;
        Long up = stats[1] != null ? ((Number) stats[1]).longValue() : 0L;
        Long down = stats[2] != null ? ((Number) stats[2]).longValue() : 0L;

        Double satisfactionRate = total > 0 ? (double) up / total * 100 : 0.0;

        Map<String, Object> result = new HashMap<>();
        result.put("totalCount", total);
        result.put("upCount", up);
        result.put("downCount", down);
        result.put("satisfactionRate", satisfactionRate);
        result.put("recentDownComments", java.util.List.of());

        return result;
    }

    /**
     * 获取消息反馈列表
     */
    @Transactional(readOnly = true)
    public java.util.List<Map<String, Object>> listForMessage(Long messageId) {
        return java.util.List.of();
    }
}
