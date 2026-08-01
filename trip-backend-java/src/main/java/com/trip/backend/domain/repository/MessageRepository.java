package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Message;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

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
}
