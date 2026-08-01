package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.AgentStep;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/**
 * AgentStep Repository
 */
public interface AgentStepRepository extends JpaRepository<AgentStep, Long> {

    Page<AgentStep> findByMessageIdOrderByStepAsc(Long messageId, Pageable pageable);

    List<AgentStep> findByMessageIdOrderByStepAsc(Long messageId);

    void deleteByMessageId(Long messageId);
}
