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

    // ==================== C2 RAG 检索 ====================

    /**
     * 全文检索（to_tsvector + websearch_to_tsquery）
     */
    @Query(value = "SELECT * FROM spots s WHERE to_tsvector('chinese', s.name || ' ' || s.description) @@ websearch_to_tsquery('chinese', :query) ORDER BY ts_rank_cd(to_tsvector('chinese', s.name || ' ' || s.description), websearch_to_tsquery('chinese', :query)) DESC",
        countQuery = "SELECT COUNT(*) FROM spots s WHERE to_tsvector('chinese', s.name || ' ' || s.description) @@ websearch_to_tsquery('chinese', :query)",
        nativeQuery = true)
    Page<Spot> fullTextSearch(@Param("query") String query, Pageable pageable);

    /**
     * 全文检索（带城市/分类过滤）
     */
    @Query(value = "SELECT * FROM spots s WHERE s.city = :city AND s.category = :category AND to_tsvector('chinese', s.name || ' ' || s.description) @@ websearch_to_tsquery('chinese', :query) ORDER BY ts_rank_cd(to_tsvector('chinese', s.name || ' ' || s.description), websearch_to_tsquery('chinese', :query)) DESC",
        countQuery = "SELECT COUNT(*) FROM spots s WHERE s.city = :city AND s.category = :category AND to_tsvector('chinese', s.name || ' ' || s.description) @@ websearch_to_tsquery('chinese', :query)",
        nativeQuery = true)
    Page<Spot> fullTextSearch(@Param("city") String city, @Param("category") String category, @Param("query") String query, Pageable pageable);

    /**
     * 评分降序查询
     */
    @Query("SELECT s FROM Spot s WHERE (:city IS NULL OR s.city = :city) AND (:category IS NULL OR s.category = :category) ORDER BY s.rating DESC NULLS LAST")
    Page<Spot> findByRatingDesc(@Param("city") String city, @Param("category") String category, Pageable pageable);

    /**
     * LIKE 降级检索
     */
    @Query("SELECT s FROM Spot s WHERE (LOWER(s.name) LIKE LOWER(CONCAT('%', :query, '%')) OR LOWER(s.description) LIKE LOWER(CONCAT('%', :query, '%'))) AND (:city IS NULL OR s.city = :city) AND (:category IS NULL OR s.category = :category)")
    List<Spot> findByNameContainingOrDescriptionContainingAndCityAndCategory(
        @Param("query") String query,
        @Param("city") String city,
        @Param("category") String category,
        Pageable pageable
    );
}
