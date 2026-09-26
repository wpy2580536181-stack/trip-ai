package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Trip;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

/**
 * Trip repository
 */
public interface TripRepository extends JpaRepository<Trip, Long> {

    /**
     * 根据用户ID查询行程（分页，排除子行程）
     */
    Page<Trip> findByUserIdAndParentTripIdIsNull(Long userId, Pageable pageable);

    /**
     * 根据用户ID查询行程（按创建时间倒序）
     */
    Page<Trip> findByUserIdOrderByCreatedAtDesc(Long userId, Pageable pageable);

    /**
     * 根据用户ID和状态查询行程
     */
    List<Trip> findByUserIdAndStatus(Long userId, String status);

    /**
     * 根据ID和用户ID查询行程
     */
    Optional<Trip> findByIdAndUserId(Long id, Long userId);

    /**
     * 根据ID和状态查询行程
     */
    Optional<Trip> findByIdAndStatus(Long id, String status);

    /**
     * 根据父行程ID列表和用户ID查询行程（按创建时间升序）
     */
    List<Trip> findByParentTripIdInAndUserIdOrderByCreatedAtAsc(List<Long> parentTripIds, Long userId);

    /**
     * 取用户最近一条指定状态的行程（用于 chat 改行程）。
     */
    Optional<Trip> findTopByUserIdAndStatusOrderByCreatedAtDesc(Long userId, String status);
}
