package com.trip.backend.service.tasks;

import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.repository.MessageRepository;
import com.trip.backend.service.chat.PreferenceExtractor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;

/**
 * 摘要服务
 *
 * 职责：
 * - 压缩对话摘要
 * - 追加关键决策
 */
@Service
public class SummaryService {

    private static final Logger log = LoggerFactory.getLogger(SummaryService.class);

    private final MessageRepository messageRepository;
    private final PreferenceExtractor preferenceExtractor;

    public SummaryService(MessageRepository messageRepository, PreferenceExtractor preferenceExtractor) {
        this.messageRepository = messageRepository;
        this.preferenceExtractor = preferenceExtractor;
    }

    /**
     * 压缩会话摘要
     *
     * @param conversationId 会话 ID
     * @return 摘要文本
     */
    @Transactional(readOnly = true)
    public String compressConversation(Long conversationId) {
        try {
            // 获取最近消息（最多 20 条）
            var page = messageRepository
                .findByConversationIdOrderByCreatedAtDesc(conversationId,
                    org.springframework.data.domain.PageRequest.of(0, 20));
            List<Message> messages = page.getContent();

            if (messages.isEmpty()) {
                return "";
            }

            // 拼接消息内容
            StringBuilder content = new StringBuilder();
            for (Message msg : messages) {
                content.append(msg.getRole()).append(": ").append(msg.getContent()).append("\n");
            }

            // TODO: D12 实现后补充 LLM 压缩
            // 目前返回简单摘要
            String summary = "Conversation with " + messages.size() + " messages";

            log.debug("[SummaryService] Compressed conversation: conversationId={}, summary={}",
                conversationId, summary);

            return summary;

        } catch (Exception e) {
            log.error("[SummaryService] Failed to compress conversation: conversationId={}", conversationId, e);
            return "";
        }
    }

    /**
     * 追加关键决策（is_planning 时）
     *
     * @param conversationId 会话 ID
     * @param decision 决策内容
     */
    @Transactional
    public void appendKeyDecision(Long conversationId, String decision) {
        // TODO: D12 实现后补充（追加到 conversation metadata 或独立表）
        log.debug("[SummaryService] Appending key decision: conversationId={}, decision={}",
            conversationId, decision);
    }
}
