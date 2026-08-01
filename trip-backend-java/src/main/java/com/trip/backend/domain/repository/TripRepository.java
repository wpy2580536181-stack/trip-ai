package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Trip;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

/**
 * Trip Repository
 */
public interface TripRepository extends JpaRepository<Trip, Long> {

    Page<Trip> findByUserIdOrderByCreatedAtDesc(Long userId, Pageable pageable);

    List<Trip> findByUserIdAndStatus(Long userId, String status);

    Optional<Trip> findByIdAndUserId(Long id, Long userId);

    Optional<Trip> findByIdAndStatus(Long id, String status);
}
