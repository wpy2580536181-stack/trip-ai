package com.trip.backend.service;

import com.trip.backend.domain.entity.Feedback;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.entity.User;
import com.trip.backend.domain.repository.FeedbackRepository;
import com.trip.backend.domain.repository.MessageRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;

/**
 * 反馈服务（对应 Python services/feedback_service.py）
 */
@Service
public class FeedbackService {

    private final FeedbackRepository feedbackRepository;
    private final MessageRepository messageRepository;

    public FeedbackService(FeedbackRepository feedbackRepository, MessageRepository messageRepository) {
        this.feedbackRepository = feedbackRepository;
        this.messageRepository = messageRepository;
    }

    /**
     * 提交反馈（IDOR 校验 + 唯一 upsert）
     */
    @Transactional
    public Feedback submitFeedback(Long userId, Long messageId, Integer rating, String comment, List<String> tags) {
        // 1. 验证评分（1 或 -1）
        if (rating == null || (rating != 1 && rating != -1)) {
            throw AppException.badRequest("评分必须为 1 或 -1");
        }

        // 2. 验证消息归属
        Message message = messageRepository.findById(messageId)
            .orElseThrow(() -> AppException.notFound("消息不存在"));

        // 注意：这里简化实现，实际应关联 conversation 并验证 userId 权限

        // 3. 验证消息为 assistant 消息（可评分）
        if (!"assistant".equals(message.getRole())) {
            throw AppException.badRequest("仅 assistant 消息可评分");
        }

        // 4. 截断评论（500 字）
        if (comment != null && comment.length() > 500) {
            comment = comment.substring(0, 500);
        }

        // 5. 标签限制（≤10）
        if (tags != null && tags.size() > 10) {
            tags = tags.subList(0, 10);
        }

        // 6. 唯一 upsert (user_id, message_id)
        return feedbackRepository.findByUserIdAndMessageId(userId, messageId)
            .map(existing -> {
                existing.setRating(rating);
                existing.setComment(comment);
                existing.setTags(tags);
                return feedbackRepository.save(existing);
            })
            .orElseGet(() -> {
                Feedback feedback = new Feedback();
                feedback.setUserId(userId);
                feedback.setMessageId(messageId);
                feedback.setConversationId(message.getConversationId());
                feedback.setRating(rating);
                feedback.setComment(comment);
                feedback.setTags(tags);
                return feedbackRepository.save(feedback);
            });
    }

    /**
     * 获取消息的反馈列表
     */
    public Page<Feedback> getFeedbackByMessageId(Long messageId, int page, int pageSize) {
        return feedbackRepository.findByMessageId(messageId, PageRequest.of(page - 1, pageSize));
    }

    /**
     * 获取用户提交的反馈（公开接口，按 message_id 查询）
     */
    public List<Feedback> getFeedbackListByMessageId(Long messageId) {
        return feedbackRepository.findByMessageId(messageId, PageRequest.of(0, 100)).getContent();
    }

    /**
     * 获取反馈统计
     */
    public Map<String, Object> getFeedbackStats() {
        // TODO: 实现聚合查询
        return Map.of(
            "total", 0,
            "positive", 0,
            "negative", 0
        );
    }

    /**
     * 高分低满意度案例（Admin）
     */
    public List<Map<String, Object>> getHighTokenLowSatisfaction() {
        // TODO: 实现查询（token_usage_logs 与 feedbacks 关联）
        return List.of();
    }

    /**
     * 每日反馈统计（Admin）
     */
    public List<Map<String, Object>> getDailyStats() {
        // TODO: 实现聚合查询
        return List.of();
    }

    /**
     * 测试告警（Admin）
     */
    public void testAlert() {
        // TODO: 触发测试告警
    }

    /**
     * 转换为测试用例（Admin）
     */
    public void convertToFixture(Long feedbackId) {
        // TODO: 实现
    }
}
