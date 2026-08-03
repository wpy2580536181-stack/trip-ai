package com.trip.backend.infra.db;

import java.util.List;

/**
 * 向量检索接口
 */
public interface VectorSearchRepository {

    /**
     * 按 embedding 相似度检索
     */
    List<?> searchByEmbedding(float[] embedding, String city, String category, int limit);

    /**
     * 按 embedding 检索 SpotDocs
     */
    List<?> searchSpotDocsByEmbedding(float[] embedding, Long spotId, int limit);
}
