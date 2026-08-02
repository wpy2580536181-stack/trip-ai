package com.trip.backend.service.rag;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.entity.SpotDoc;
import com.trip.backend.domain.repository.SpotDocRepository;
import com.trip.backend.infra.db.VectorSearchRepository;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 向量检索（SpotDocs）
 *
 * 对应 Python services/rag/vector_search.py
 *
 * 功能：
 * - JOIN spots 按 city 过滤
 * - 向量失败降级全文再聚合
 */
@Service
public class VectorSearchSpotDocs {

    private final VectorSearchRepository vectorSearchRepository;
    private final SpotDocRepository spotDocRepository;
    private final FulltextSearch fulltextSearch;

    public VectorSearchSpotDocs(
            VectorSearchRepository vectorSearchRepository,
            SpotDocRepository spotDocRepository,
            FulltextSearch fulltextSearch) {
        this.vectorSearchRepository = vectorSearchRepository;
        this.spotDocRepository = spotDocRepository;
        this.fulltextSearch = fulltextSearch;
    }

    /**
     * 向量检索 SpotDocs
     *
     * @param queryVector 查询向量
     * @param city 城市（可选）
     * @param limit 返回数量
     * @return SpotDoc 列表
     */
    public List<SpotDoc> search(float[] queryVector, String city, int limit) {
        try {
            // 1. 向量检索 SpotDocs（带 city 过滤）
            List<SpotDoc> results = vectorSearchRepository.searchSpotDocsByEmbedding(
                queryVector,
                city,
                limit
            );

            if (results != null && !results.isEmpty()) {
                return results;
            }

            // 2. 降级：全文检索 spots，再关联 spot_docs
            return fallbackToFulltext(city, limit);

        } catch (Exception e) {
            // 向量失败，降级全文
            return fallbackToFulltext(city, limit);
        }
    }

    /**
     * 降级：全文检索 spots → 关联 spot_docs
     */
    private List<SpotDoc> fallbackToFulltext(String city, int limit) {
        try {
            // 全文检索 spots
            List<Spot> spots = fulltextSearch.search("", city, null, limit);

            // 关联 spot_docs
            return spots.stream()
                .map(spot -> spotDocRepository.findBySpotId(spot.getId()).orElse(null))
                .filter(java.util.Objects::nonNull)
                .limit(limit)
                .collect(Collectors.toList());

        } catch (Exception e) {
            return List.of();
        }
    }
}
