package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.TokenUsageLog;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

/**
 * TokenUsageLog Repository
 */
public interface TokenUsageLogRepository extends JpaRepository<TokenUsageLog, Long> {

    Page<TokenUsageLog> findByUserIdOrderByCreatedAtDesc(Long userId, Pageable pageable);

    @Query("SELECT SUM(t.totalTokens) FROM TokenUsageLog t WHERE t.userId = :userId AND t.createdAt >= :since")
    Optional<Long> sumTotalTokensByUserIdSince(@Param("userId") Long userId,
                                               @Param("since") OffsetDateTime since);

    @Query("SELECT SUM(t.totalTokens) FROM TokenUsageLog t WHERE t.createdAt >= :since")
    Optional<Long> sumTotalTokensSince(@Param("since") OffsetDateTime since);

    List<TokenUsageLog> findByUserIdAndRequestTypeAndCreatedAtBetween(
        Long userId, String requestType, OffsetDateTime start, OffsetDateTime end);
}
