package com.trip.backend.domain.repository;

import com.trip.backend.domain.entity.SpotDoc;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

/**
 * SpotDoc Repository
 */
public interface SpotDocRepository extends JpaRepository<SpotDoc, Long> {

    Page<SpotDoc> findBySpotId(Long spotId, Pageable pageable);

    Page<SpotDoc> findBySpot_City(String city, Pageable pageable);

    Page<SpotDoc> findBySourceType(String sourceType, Pageable pageable);

    Page<SpotDoc> findBySpot_CityAndSourceType(String city, String sourceType, Pageable pageable);
}
