package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Feedback;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Feedback Repository
 */
public interface FeedbackRepository extends JpaRepository<Feedback, Long> {

    Optional<Feedback> findByUserIdAndMessageId(Long userId, Long messageId);

    Page<Feedback> findByMessageId(Long messageId, Pageable pageable);

    Page<Feedback> findByUserId(Long userId, Pageable pageable);
}
