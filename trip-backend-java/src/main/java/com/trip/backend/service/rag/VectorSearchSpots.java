package com.trip.backend.service.rag;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.infra.db.VectorSearchRepository;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 向量检索（Spots）
 *
 * 对应 Python services/rag/vector_search.py
 *
 * 功能：
 * - `1 - (embedding <=> CAST(:vec AS vector))` 相似度计算
 * - embedding IS NOT NULL 过滤
 * - city/category 过滤
 * - 失败降级全文检索
 */
@Service
public class VectorSearchSpots {

    private final VectorSearchRepository vectorSearchRepository;
    private final FulltextSearch fulltextSearch;

    public VectorSearchSpots(VectorSearchRepository vectorSearchRepository, FulltextSearch fulltextSearch) {
        this.vectorSearchRepository = vectorSearchRepository;
        this.fulltextSearch = fulltextSearch;
    }

    /**
     * 向量检索
     *
     * @param queryVector 查询向量
     * @param city 城市（可选）
     * @param category 分类（可选）
     * @param limit 返回数量
     * @return 景点列表（按相似度降序）
     */
    public List<Spot> search(float[] queryVector, String city, String category, int limit) {
        try {
            List<Spot> results = vectorSearchRepository.searchByEmbedding(
                queryVector,
                city,
                category,
                limit
            );

            if (results != null && !results.isEmpty()) {
                return results;
            }

            // 降级：全文检索
            return fulltextSearch.search("", city, category, limit);

        } catch (Exception e) {
            // 向量检索失败，降级全文
            return fulltextSearch.search("", city, category, limit);
        }
    }
}
