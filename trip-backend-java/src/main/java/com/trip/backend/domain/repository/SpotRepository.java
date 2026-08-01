package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.Spot;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

/**
 * Spot Repository
 */
public interface SpotRepository extends JpaRepository<Spot, Long> {

    Page<Spot> findByCityAndCategory(String city, String category, Pageable pageable);

    Page<Spot> findByCity(String city, Pageable pageable);

    Optional<Spot> findByIdAndCity(Long id, String city);

    @Query("SELECT COUNT(s) FROM Spot s WHERE s.city = :city")
    long countByCity(@Param("city") String city);
}
