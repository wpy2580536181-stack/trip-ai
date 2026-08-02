package com.trip.backend.service.chat;

import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.entity.Conversation;
import com.trip.backend.domain.repository.MessageRepository;
import com.trip.backend.domain.repository.ConversationRepository;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 消息持久化服务（对应 Python services/trip_service.py 落库逻辑）
 *
 * 职责：
 * - user 消息立即落库
 * - assistant 消息 3s 增量 flush
 * - 标题截断（首条消息前 20 字符）
 * - complete 事件附 usage 字段
 */
@Service
public class MessagePersistenceService {

    private final MessageRepository messageRepository;
    private final ConversationRepository conversationRepository;

    // 待 flush 的 assistant 消息缓存（messageId → contentBuilder）
    private final Map<Long, StringBuilder> pendingFlush = new ConcurrentHashMap<>();

    // 待 flush 的 metadata 缓存
    private final Map<Long, Map<String, Object>> pendingMetadata = new ConcurrentHashMap<>();

    public MessagePersistenceService(
            MessageRepository messageRepository,
            ConversationRepository conversationRepository) {
        this.messageRepository = messageRepository;
        this.conversationRepository = conversationRepository;
    }

    // ==================== 立即落库 ====================

    /**
     * user 消息立即落库
     *
     * @return 落库后的 Message 实体
     */
    @Transactional
    public Message persistUserMessage(Long userId, Long conversationId, String content) {
        Message message = new Message();
        message.setUserId(userId);
        message.setConversationId(conversationId);
        message.setRole("user");
        message.setContent(content);
        message.setMetadata(null);

        Message saved = messageRepository.save(message);

        // 如果是首条用户消息，更新会话标题（截断前 20 字符）
        if (conversationId != null) {
            updateConversationTitle(conversationId, content);
        }

        return saved;
    }

    /**
     * assistant 消息先建空行取 id（用于后续增量更新）
     *
     * @return 空消息实体（id 已生成）
     */
    @Transactional
    public Message createEmptyAssistantMessage(Long userId, Long conversationId) {
        Message message = new Message();
        message.setUserId(userId);
        message.setConversationId(conversationId);
        message.setRole("assistant");
        message.setContent("");
        message.setMetadata(null);

        return messageRepository.save(message);
    }

    // ==================== 增量 Flush ====================

    /**
     * 追加 assistant 消息内容（缓存，等待 3s flush）
     */
    public void appendAssistantContent(Long messageId, String chunk) {
        pendingFlush.computeIfAbsent(messageId, k -> new StringBuilder())
            .append(chunk);
    }

    /**
     * 更新 assistant 消息 metadata（缓存）
     */
    public void updateAssistantMetadata(Long messageId, Map<String, Object> metadata) {
        pendingMetadata.put(messageId, metadata);
    }

    /**
     * 定时 flush（每 3s）
     * - 更新 content
     * - 更新 metadata
     * - 清理缓存
     */
    @Scheduled(fixedRate = 3000)
    @Transactional
    public void flushPendingMessages() {
        if (pendingFlush.isEmpty()) {
            return;
        }

        // 快照当前待 flush 数据
        Map<Long, String> toFlush = new java.util.LinkedHashMap<>();
        pendingFlush.forEach((id, builder) -> {
            toFlush.put(id, builder.toString());
        });

        // 批量更新
        toFlush.forEach((messageId, content) -> {
            messageRepository.updateContentById(messageId, content);

            // 更新 metadata
            Map<String, Object> metadata = pendingMetadata.get(messageId);
            if (metadata != null) {
                messageRepository.updateMetadataById(messageId, metadata);
                pendingMetadata.remove(messageId);
            }
        });

        // 清理已 flush 的缓存
        pendingFlush.keySet().removeAll(toFlush.keySet());
    }

    /**
     * 强制 flush（complete/error 时调用）
     *
     * @param messageId 消息 ID
     * @param usage token 用量（null 表示不更新）
     */
    @Transactional
    public void forceFlush(Long messageId, Object usage) {
        // 更新 content
        StringBuilder builder = pendingFlush.remove(messageId);
        if (builder != null && !builder.isEmpty()) {
            messageRepository.updateContentById(messageId, builder.toString());
        }

        // 更新 metadata（附 usage）
        Map<String, Object> metadata = pendingMetadata.remove(messageId);
        if (metadata != null && usage != null) {
            metadata.put("usage", usage);
            messageRepository.updateMetadataById(messageId, metadata);
        } else if (usage != null && metadata == null) {
            // metadata 为空时创建
            Map<String, Object> newMetadata = Map.of("usage", usage);
            messageRepository.updateMetadataById(messageId, newMetadata);
        }
    }

    // ==================== 辅助方法 ====================

    /**
     * 更新会话标题（首条消息前 20 字符）
     */
    private void updateConversationTitle(Long conversationId, String firstMessage) {
        if (firstMessage == null || firstMessage.isBlank()) {
            return;
        }

        Conversation conversation = conversationRepository.findById(conversationId).orElse(null);
        if (conversation == null) {
            return;
        }

        // 空标题或"新对话"才更新
        String currentTitle = conversation.getTitle();
        if (currentTitle != null
            && !currentTitle.isBlank()
            && !"新对话".equals(currentTitle)) {
            return;
        }

        // 截断前 20 字符
        String title = firstMessage.length() <= 20
            ? firstMessage
            : firstMessage.substring(0, 20) + "...";

        conversation.setTitle(title);
        conversationRepository.save(conversation);
    }
}
