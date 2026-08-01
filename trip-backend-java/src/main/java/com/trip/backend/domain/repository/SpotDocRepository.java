package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.SpotDoc;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

/**
 * SpotDoc Repository
 */
public interface SpotDocRepository extends JpaRepository<SpotDoc, Long> {

    Page<SpotDoc> findBySpotId(Long spotId, Pageable pageable);

    @Query("SELECT COUNT(sd) FROM SpotDoc sd WHERE sd.spotId = :spotId")
    long countBySpotId(@Param("spotId") Long spotId);

    @Query("SELECT sd FROM SpotDoc sd WHERE sd.spotId IN :spotIds")
    List<SpotDoc> findBySpotIdIn(@Param("spotIds") Iterable<Long> spotIds);

    @Query("SELECT sd FROM SpotDoc sd JOIN Spot s ON sd.spotId = s.id WHERE s.city = :city AND sd.sourceType = :sourceType")
    Page<SpotDoc> findByCityAndSourceType(@Param("city") String city,
                                          @Param("sourceType") String sourceType,
                                          Pageable pageable);
}
