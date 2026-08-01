package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Conversation;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Conversation Repository
 */
public interface ConversationRepository extends JpaRepository<Conversation, Long> {

    Page<Conversation> findByUserIdOrderByUpdatedAtDesc(Long userId, Pageable pageable);

    List<Conversation> findByUserIdOrderByUpdatedAtDesc(Long userId);

    Optional<Conversation> findByIdAndUserId(Long id, Long userId);
}
