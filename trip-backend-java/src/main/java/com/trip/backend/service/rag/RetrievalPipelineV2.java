package com.trip.backend.service.rag;

import com.trip.backend.domain.entity.Spot;
import com.trip.backend.domain.entity.SpotDoc;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.stream.Collectors;

/**
 * 扩展检索流水线（四路召回 + credibility 重排）
 *
 * 对应 Python services/rag/retrieval_pipeline.py（C3 增强版）
 *
 * 四路：
 * 1. pg_fulltext（权重 W1）
 * 2. rating（权重 W2）
 * 3. vector_spots（权重 W3）
 * 4. vector_spot_docs（权重 W4）
 *
 * 后续：RerankWithCredibility 重排
 */
@Service
public class RetrievalPipelineV2 {

    private final QueryRewriter queryRewriter;
    private final RatingSearch ratingSearch;
    private final FulltextSearch fulltextSearch;
    private final VectorSearchSpots vectorSearchSpots;
    private final VectorSearchSpotDocs vectorSearchSpotDocs;
    private final Rrf rrf;
    private final RerankWithCredibility rerankWithCredibility;

    // RRF 权重（可配置）
    private static final double FULLTEXT_WEIGHT = 0.7;
    private static final double RATING_WEIGHT = 0.5;
    private static final double VECTOR_SPOTS_WEIGHT = 0.6;
    private static final double VECTOR_DOCS_WEIGHT = 0.4;
    private static final int RRF_K = 60;
    private static final int DEFAULT_LIMIT = 5;

    public RetrievalPipelineV2(
            QueryRewriter queryRewriter,
            RatingSearch ratingSearch,
            FulltextSearch fulltextSearch,
            VectorSearchSpots vectorSearchSpots,
            VectorSearchSpotDocs vectorSearchSpotDocs,
            Rrf rrf,
            RerankWithCredibility rerankWithCredibility) {
        this.queryRewriter = queryRewriter;
        this.ratingSearch = ratingSearch;
        this.fulltextSearch = fulltextSearch;
        this.vectorSearchSpots = vectorSearchSpots;
        this.vectorSearchSpotDocs = vectorSearchSpotDocs;
        this.rrf = rrf;
        this.rerankWithCredibility = rerankWithCredibility;
    }

    /**
     * 四路召回检索
     *
     * @param query 原始查询
     * @param queryVector 查询向量（可选）
     * @param city 城市（可选）
     * @param category 分类（可选）
     * @param limit 返回数量
     * @return 检索结果列表（Spots）
     */
    public List<Spot> search(String query, float[] queryVector, String city, String category, int limit) {
        // 1. 查询改写
        String rewritten = queryRewriter.rewriteQuery(query, city);

        try {
            List<Spot> results;

            // 2. 四路召回
            if (queryVector != null && queryVector.length > 0) {
                // 四路：rating + fulltext + vector_spots + vector_docs
                List<Spot> ratingResults = ratingSearch.search(city, category, limit * 2);
                List<Spot> fulltextResults = fulltextSearch.search(rewritten, city, category, limit * 2);
                List<Spot> vectorSpotResults = vectorSearchSpots.search(queryVector, city, category, limit * 2);

                // vector_spot_docs 结果转换为 Spot（通过 spot_id 关联）
                List<SpotDoc> spotDocs = vectorSearchSpotDocs.search(queryVector, city, limit * 2);
                List<Spot> vectorDocResults = spotDocs.stream()
                    .map(SpotDoc::getSpotId)
                    .distinct()
                    .limit(limit * 2)
                    .map(id -> new Spot()) // TODO: 查询真实 Spot
                    .collect(Collectors.toList());

                // 加权 RRF 融合
                List<List<Spot>> resultsList = List.of(
                    fulltextResults,
                    ratingResults,
                    vectorSpotResults,
                    vectorDocResults
                );
                List<Double> weights = List.of(
                    FULLTEXT_WEIGHT,
                    RATING_WEIGHT,
                    VECTOR_SPOTS_WEIGHT,
                    VECTOR_DOCS_WEIGHT
                );

                results = rrf.mergeWithWeights(resultsList, weights, RRF_K, "id");

            } else {
                // 双路回退：rating + fulltext
                List<Spot> ratingResults = ratingSearch.search(city, category, limit * 2);
                List<Spot> fulltextResults = fulltextSearch.search(rewritten, city, category, limit * 2);

                List<List<Spot>> resultsList = List.of(fulltextResults, ratingResults);
                List<Double> weights = List.of(FULLTEXT_WEIGHT, RATING_WEIGHT);

                results = rrf.mergeWithWeights(resultsList, weights, RRF_K, "id");
            }

            // 3. 截断
            return results.subList(0, Math.min(results.size(), limit));

        } catch (Exception e) {
            // 降级到 C2 双路
            return fallbackToTwoWay(rewritten, city, category, limit);
        }
    }

    /**
     * 降级到双路
     */
    private List<Spot> fallbackToTwoWay(String query, String city, String category, int limit) {
        try {
            List<Spot> ratingResults = ratingSearch.search(city, category, limit);
            List<Spot> fulltextResults = fulltextSearch.search(query, city, category, limit);

            List<List<Spot>> resultsList = List.of(fulltextResults, ratingResults);
            List<Double> weights = List.of(FULLTEXT_WEIGHT, RATING_WEIGHT);

            return rrf.mergeWithWeights(resultsList, weights, RRF_K, "id")
                .subList(0, Math.min(limit, Math.min(fulltextResults.size(), ratingResults.size())));

        } catch (Exception e) {
            return List.of();
        }
    }

    /**
     * 默认检索
     */
    public List<Spot> search(String query, String city, String category) {
        return search(query, null, city, category, DEFAULT_LIMIT);
    }
}
