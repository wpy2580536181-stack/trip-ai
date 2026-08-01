package com.trip.backend.service;

import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.repository.ConversationRepository;
import com.trip.backend.domain.repository.MessageRepository;
import com.trip.backend.utils.AppException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 会话服务（对应 Python services/conversation_service.py）
 */
@Service
public class ConversationService {

    private final ConversationRepository conversationRepository;
    private final MessageRepository messageRepository;

    public ConversationService(ConversationRepository conversationRepository,
                              MessageRepository messageRepository) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
    }

    /**
     * 获取会话列表
     */
    public Page<Conversation> getConversations(Long userId, int page, int pageSize) {
        return conversationRepository.findByUserIdOrderByUpdatedAtDesc(
            userId, PageRequest.of(page - 1, pageSize)
        );
    }

    /**
     * 获取会话详情（含消息）
     */
    public ConversationWithMessages getConversation(Long userId, Long conversationId) {
        Conversation conversation = conversationRepository.findByIdAndUserId(conversationId, userId)
            .orElseThrow(() -> AppException.notFound("会话不存在"));

        List<Message> messages = messageRepository
            .findByConversationIdAndExcludedFromContextFalseOrderByCreatedAtAsc(conversationId);

        return new ConversationWithMessages(conversation, messages);
    }

    /**
     * 创建会话
     */
    @Transactional
    public Conversation createConversation(Long userId, String title) {
        Conversation conversation = new Conversation();
        conversation.setUserId(userId);
        conversation.setTitle(title != null && !title.isBlank() ? title : "新对话");
        return conversationRepository.save(conversation);
    }

    /**
     * 删除会话（级联删除消息）
     */
    @Transactional
    public void deleteConversation(Long userId, Long conversationId) {
        Conversation conversation = conversationRepository.findByIdAndUserId(conversationId, userId)
            .orElseThrow(() -> AppException.notFound("会话不存在"));
        conversationRepository.delete(conversation);
    }

    /**
     * 更新会话标题
     */
    public Conversation updateTitle(Long userId, Long conversationId, String title) {
        Conversation conversation = conversationRepository.findByIdAndUserId(conversationId, userId)
            .orElseThrow(() -> AppException.notFound("会话不存在"));
        conversation.setTitle(title);
        return conversationRepository.save(conversation);
    }

    public record ConversationWithMessages(Conversation conversation, List<Message> messages) {}
}
