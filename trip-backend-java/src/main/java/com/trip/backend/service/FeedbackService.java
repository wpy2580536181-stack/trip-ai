package com.trip.backend.service;

import com.trip.backend.domain.entity.Feedback;
import com.trip.backend.domain.repository.FeedbackRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;

/**
 * Feedback service（简化版）
 */
@Service
public class FeedbackService {

    private final FeedbackRepository feedbackRepository;

    public FeedbackService(FeedbackRepository feedbackRepository) {
        this.feedbackRepository = feedbackRepository;
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
    public Feedback submitFeedback(Long userId, Long messageId, Integer rating, 
                                    String comment, java.util.List<String> tags) {
        return feedbackRepository.findByUserIdAndMessageId(userId, messageId)
            .map(existing -> {
                existing.setRating(rating);
                existing.setComment(comment);
                existing.setTags(tags);
                return existing;
            })
            .orElseGet(() -> {
                Feedback feedback = new Feedback(userId, messageId, rating);
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
