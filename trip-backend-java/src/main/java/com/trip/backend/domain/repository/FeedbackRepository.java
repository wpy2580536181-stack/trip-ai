package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Feedback;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

/**
 * Feedback Repository
 */
public interface FeedbackRepository extends JpaRepository<Feedback, Long> {

    Page<Feedback> findByUserIdOrderByCreatedAtDesc(Long userId, Pageable pageable);

    Optional<Feedback> findByUserIdAndMessageId(Long userId, Long messageId);

    @Query("SELECT COUNT(f) FROM Feedback f WHERE f.messageId = :messageId")
    long countByMessageId(@Param("messageId") Long messageId);

    @Query("SELECT SUM(CASE WHEN f.rating = 1 THEN 1 ELSE 0 END), " +
           "SUM(CASE WHEN f.rating = -1 THEN 1 ELSE 0 END), " +
           "COUNT(f) FROM Feedback f WHERE f.messageId = :messageId")
    Object[] getStatsByMessageId(@Param("messageId") Long messageId);

    @Query("SELECT COUNT(f), " +
           "SUM(CASE WHEN f.rating = 1 THEN 1 ELSE 0 END), " +
           "SUM(CASE WHEN f.rating = -1 THEN 1 ELSE 0 END) " +
           "FROM Feedback f WHERE f.createdAt >= :since")
    Object[] getGlobalStats(@Param("since") java.time.OffsetDateTime since);
}
