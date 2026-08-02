package com.trip.backend.service.rag;

import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;

/**
 * 检索流水线
 *
 * 对应 Python services/rag/retrieval_pipeline.py
 *
 * 流程：
 * 1. 查询改写（QueryRewriter）
 * 2. 双路召回（Rating + Fulltext）
 * 3. 加权 RRF 融合（0.7/0.5）
 * 4. 截断 limit=5
 */
@Service
public class RetrievalPipeline {

    private final QueryRewriter queryRewriter;
    private final RatingSearch ratingSearch;
    private final FulltextSearch fulltextSearch;
    private final Rrf rrf;

    // RRF 权重
    private static final double FULLTEXT_WEIGHT = 0.7;
    private static final double RATING_WEIGHT = 0.5;
    private static final int RRF_K = 60;
    private static final int DEFAULT_LIMIT = 5;

    public RetrievalPipeline(
            QueryRewriter queryRewriter,
            RatingSearch ratingSearch,
            FulltextSearch fulltextSearch,
            Rrf rrf) {
        this.queryRewriter = queryRewriter;
        this.ratingSearch = ratingSearch;
        this.fulltextSearch = fulltextSearch;
        this.rrf = rrf;
    }

    /**
     * 执行检索流水线
     *
     * @param query 原始查询
     * @param city 城市（可选）
     * @param category 分类（可选）
     * @param limit 返回数量（默认 5）
     * @return 检索结果列表
     */
    public List<Spot> search(String query, String city, String category, int limit) {
        // 1. 查询改写
        String rewritten = queryRewriter.rewriteQuery(query, city);

        try {
            // 2. 双路召回
            List<Spot> ratingResults = ratingSearch.search(city, category, limit * 2);
            List<Spot> fulltextResults = fulltextSearch.search(rewritten, city, category, limit * 2);

            // 3. 加权 RRF 融合
            List<List<Spot>> resultsList = List.of(fulltextResults, ratingResults);
            List<Double> weights = List.of(FULLTEXT_WEIGHT, RATING_WEIGHT);

            List<Spot> merged = rrf.mergeWithWeights(resultsList, weights, RRF_K, "id");

            // 4. 截断
            return merged.subList(0, Math.min(merged.size(), limit));

        } catch (Exception e) {
            // 降级：如果某一路失败，只返回另一路
            return fallbackSearch(rewritten, city, category, limit);
        }
    }

    /**
     * 降级检索
     */
    private List<Spot> fallbackSearch(String query, String city, String category, int limit) {
        try {
            List<Spot> fulltextResults = fulltextSearch.search(query, city, category, limit);
            if (fulltextResults != null && !fulltextResults.isEmpty()) {
                return fulltextResults.subList(0, Math.min(fulltextResults.size(), limit));
            }
        } catch (Exception e) {
            // 忽略
        }

        try {
            List<Spot> ratingResults = ratingSearch.search(city, category, limit);
            if (ratingResults != null && !ratingResults.isEmpty()) {
                return ratingResults.subList(0, Math.min(ratingResults.size(), limit));
            }
        } catch (Exception e) {
            // 忽略
        }

        return Collections.emptyList();
    }

    /**
     * 默认检索（limit=5）
     */
    public List<Spot> search(String query, String city, String category) {
        return search(query, city, category, DEFAULT_LIMIT);
    }
}
