package com.trip.backend.service.rag;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.repository.SpotRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 全文检索
 *
 * 对应 Python services/rag/fulltext_search.py
 *
 * 功能：
 * - to_tsvector('chinese', ...) @@ websearch_to_tsquery('chinese', :q)
 * - LIKE 降级
 */
@Service
public class FulltextSearch {

    private final SpotRepository spotRepository;

    public FulltextSearch(SpotRepository spotRepository) {
        this.spotRepository = spotRepository;
    }

    /**
     * 全文检索
     *
     * @param query 查询文本
     * @param city 城市（可选）
     * @param category 分类（可选）
     * @param limit 返回数量
     * @return 景点列表
     */
    public List<Spot> search(String query, String city, String category, int limit) {
        try {
            // 使用 JPA 原生查询（to_tsvector + websearch_to_tsquery）
            List<Spot> results = spotRepository.fullTextSearch(
                query,
                city,
                category,
                PageRequest.of(0, limit)
            );

            if (results != null && !results.isEmpty()) {
                return results;
            }

            // 降级：LIKE
            return spotRepository.findByNameContainingOrDescriptionContainingAndCityAndCategory(
                query,
                query,
                city,
                category,
                PageRequest.of(0, limit)
            );

        } catch (Exception e) {
            // 全文检索失败，降级到 LIKE
            return spotRepository.findByNameContainingOrDescriptionContainingAndCityAndCategory(
                query,
                query,
                city,
                category,
                PageRequest.of(0, limit)
            );
        }
    }
}
