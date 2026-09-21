package com.trip.backend.service.rag;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * RAG 多路召回检索管线（对应 Python KnowledgeService.search_spots 的双路形态）。
 *
 * 当前双路召回：
 * - 路径 rating：评分排序（基础召回）
 * - 路径 pg_fulltext：PostgreSQL tsvector 全文检索（失败自动降级 LIKE）
 *
 * 融合：加权 RRF（fulltext=0.7, rating=0.5, k=60）；加权失败 → 降级普通 RRF。
 * 各路径独立失败/超时 → 跳过该路径，其余路径仍出结果（降级链）。
 */
@Component
public class RetrievalPipeline {

    private static final Logger log = LoggerFactory.getLogger(RetrievalPipeline.class);

    private static final double WEIGHT_FULLTEXT = 0.7;
    private static final double WEIGHT_RATING = 0.5;

    private final QueryRewriter queryRewriter;
    private final RatingSearch ratingSearch;
    private final FulltextSearch fulltextSearch;
    private final int limit;

    public RetrievalPipeline(QueryRewriter queryRewriter,
                             RatingSearch ratingSearch,
                             FulltextSearch fulltextSearch,
                             @Value("${rag.retrieval.limit:5}") int limit) {
        this.queryRewriter = queryRewriter;
        this.ratingSearch = ratingSearch;
        this.fulltextSearch = fulltextSearch;
        this.limit = limit;
    }

    /**
     * 多路召回 + RRF 融合检索 spots。
     *
     * @param query    用户查询文本
     * @param city     目标城市（可空）
     * @param category 景点类型（英文，可空）
     * @return 按相关性排序的结果（最多 limit 条），每项含 _rrf_score 与 _source
     */
    public List<Map<String, Object>> retrieve(String query, String city, String category, int limit) {
        int targetLimit = limit > 0 ? limit : this.limit;
        String rewritten = queryRewriter.rewrite(query, city, null);
        List<String> keywords = queryRewriter.extractKeywords(query);
        log.info("rag_retrieval_start query={} rewritten={} city={} category={} limit={}",
            query, rewritten, city, category, targetLimit);

        // 双路召回（每路召回 2 倍数量供融合排序）
        List<Map<String, Object>> pathFulltext = fulltextSearch.search(List.of(query), city, category, targetLimit * 2);
        List<Map<String, Object>> pathRating = ratingSearch.search(city, category, targetLimit * 2);
        log.info("rag_recall_done pg_fulltext={} rating={}", pathFulltext.size(), pathRating.size());

        List<List<Map<String, Object>>> paths = new ArrayList<>();
        paths.add(pathFulltext);
        paths.add(pathRating);

        // 加权 RRF 融合；失败降级普通 RRF
        List<Map<String, Object>> fused;
        try {
            fused = Rrf.rrfMergeWithWeights(paths, List.of(WEIGHT_FULLTEXT, WEIGHT_RATING), Rrf.DEFAULT_K, "id");
        } catch (Exception e) {
            log.warn("weighted_rrf_failed，降级普通 RRF error={}", e.getMessage());
            fused = Rrf.rrfMerge(paths, Rrf.DEFAULT_K, "id");
        }
        log.info("rag_rrf_done fused={}", fused.size());

        if (fused.isEmpty()) {
            return List.of();
        }
        return fused.subList(0, Math.min(targetLimit, fused.size()));
    }

    public int getLimit() {
        return limit;
    }
}
