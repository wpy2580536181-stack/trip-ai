package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.SpotDoc;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

/**
 * SpotDoc Repository
 */
public interface SpotDocRepository extends JpaRepository<SpotDoc, Long> {

    Page<SpotDoc> findBySpotId(Long spotId, Pageable pageable);

    @Query("SELECT sd FROM SpotDoc sd JOIN Spot s ON sd.spotId = s.id WHERE s.city = :city")
    Page<SpotDoc> findByCityUsingJoin(@Param("city") String city, Pageable pageable);

    @Query("SELECT sd FROM SpotDoc sd JOIN Spot s ON sd.spotId = s.id WHERE s.city = :city AND sd.sourceType = :sourceType")
    Page<SpotDoc> findByCityAndSourceTypeUsingJoin(@Param("city") String city,
                                                   @Param("sourceType") String sourceType,
                                                   Pageable pageable);

    Page<SpotDoc> findBySourceType(String sourceType, Pageable pageable);
}
