package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Message;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

/**
 * Message Repository
 */
public interface MessageRepository extends JpaRepository<Message, Long> {

    Page<Message> findByConversationIdAndExcludedFromContextFalseOrderByCreatedAtAsc(
        Long conversationId, Pageable pageable);

    List<Message> findByConversationIdAndExcludedFromContextFalseOrderByCreatedAtAsc(
        Long conversationId);

    Optional<Message> findByIdAndConversationId(Long id, Long conversationId);

    Page<Message> findByConversationIdOrderByCreatedAtDesc(Long conversationId, Pageable pageable);

    // ==================== D4 增量更新 ====================

    @Modifying
    @Query("UPDATE Message m SET m.content = :content WHERE m.id = :id")
    void updateContentById(@Param("id") Long id, @Param("content") String content);

    @Modifying
    @Query("UPDATE Message m SET m.metadata = :metadata WHERE m.id = :id")
    void updateMetadataById(@Param("id") Long id, @Param("metadata") Map<String, Object> metadata);
}
