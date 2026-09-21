package com.trip.backend.service.rag;

import com.trip.backend.infra.ai.BgeEmbedder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * RAG 多路召回检索管线（对应 Python KnowledgeService.search_spots）。
 *
 * 双路（开关关）：rating + pg_fulltext（tsvector，失败自动降级 LIKE）
 * 四路（开关开）：+ spots_vector（pgvector spots）+ spot_docs_vector（pgvector spot_docs 聚合到 spot 级）
 *
 * 融合：加权 RRF（fulltext=0.7, rating=0.5, spots_vector=0.5, spot_docs_vector=0.3, k=60）
 * + credibility 调节器（spot_docs 路带 credibility_score 被加权，其余路乘数 1.0）；
 * 加权失败 → 降级普通 RRF。
 * 四路模式启用 Cross-Encoder 重排（模型不可用 → 降级 RRF 顺序，按 credibility 微调）。
 *
 * 降级链：embedding 不可用 / 向量 SQL 失败 → 跳过向量路，双路仍出结果。
 */
@Component
public class RetrievalPipeline {

    private static final Logger log = LoggerFactory.getLogger(RetrievalPipeline.class);

    private static final double WEIGHT_FULLTEXT = 0.7;
    private static final double WEIGHT_RATING = 0.5;
    private static final double WEIGHT_SPOTS_VECTOR = 0.5;
    private static final double WEIGHT_SPOT_DOCS_VECTOR = 0.3;

    private final QueryRewriter queryRewriter;
    private final RatingSearch ratingSearch;
    private final FulltextSearch fulltextSearch;
    private final BgeEmbedder embedder;
    private final VectorSearchSpots vectorSearchSpots;
    private final VectorSearchSpotDocs vectorSearchSpotDocs;
    private final CredibilityService credibilityService;
    private final RerankWithCredibility rerankWithCredibility;
    private final boolean fourWayEnabled;
    private final int limit;

    /** 测试/审计计数：最近一次检索实际尝试的路径数（双路=2，四路=4）。 */
    private volatile int lastAttemptedPathCount;
    /** 最近一次检索实际参与融合的路径数（空路径被跳过）。 */
    private volatile int lastFusedPathCount;
    /** 最近一次检索是否执行了 Cross-Encoder 重排。 */
    private volatile boolean lastReranked;

    /** 双路构造（测试 / 四路关闭）。 */
    public RetrievalPipeline(QueryRewriter queryRewriter,
                             RatingSearch ratingSearch,
                             FulltextSearch fulltextSearch,
                             int limit) {
        this(queryRewriter, ratingSearch, fulltextSearch,
            null, null, null, null, null, false, limit);
    }

    @Autowired
    public RetrievalPipeline(QueryRewriter queryRewriter,
                             RatingSearch ratingSearch,
                             FulltextSearch fulltextSearch,
                             BgeEmbedder embedder,
                             VectorSearchSpots vectorSearchSpots,
                             VectorSearchSpotDocs vectorSearchSpotDocs,
                             CredibilityService credibilityService,
                             RerankWithCredibility rerankWithCredibility,
                             @Value("${rag.four-way.enabled:false}") boolean fourWayEnabled,
                             @Value("${rag.retrieval.limit:5}") int limit) {
        this.queryRewriter = queryRewriter;
        this.ratingSearch = ratingSearch;
        this.fulltextSearch = fulltextSearch;
        this.embedder = embedder;
        this.vectorSearchSpots = vectorSearchSpots;
        this.vectorSearchSpotDocs = vectorSearchSpotDocs;
        this.credibilityService = credibilityService;
        this.rerankWithCredibility = rerankWithCredibility;
        this.fourWayEnabled = fourWayEnabled;
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
        log.info("rag_retrieval_start query={} rewritten={} city={} category={} limit={} fourWay={}",
            query, rewritten, city, category, targetLimit, fourWayEnabled);

        // 双路召回（每路召回 2 倍数量供融合排序）
        List<Map<String, Object>> pathFulltext = fulltextSearch.search(List.of(query), city, category, targetLimit * 2);
        List<Map<String, Object>> pathRating = ratingSearch.search(city, category, targetLimit * 2);
        lastAttemptedPathCount = 2;

        List<List<Map<String, Object>>> paths = new ArrayList<>();
        List<Double> weights = new ArrayList<>();
        paths.add(pathFulltext);
        weights.add(WEIGHT_FULLTEXT);
        paths.add(pathRating);
        weights.add(WEIGHT_RATING);

        // 四路：+ spots_vector + spot_docs_vector（embedding 不可用 / SQL 失败 → 自动回退双路）
        if (fourWayEnabled && embedder != null && vectorSearchSpots != null && vectorSearchSpotDocs != null) {
            lastAttemptedPathCount = 4;
            Optional<float[]> queryVec = embedder.embed(query);
            if (queryVec.isPresent()) {
                float[] vec = queryVec.get();
                List<Map<String, Object>> pathSpotsVec =
                    vectorSearchSpots.search(vec, city, category, targetLimit * 2);
                List<Map<String, Object>> pathDocsVec =
                    vectorSearchSpotDocs.search(vec, city, targetLimit * 2);
                if (!pathSpotsVec.isEmpty()) {
                    paths.add(pathSpotsVec);
                    weights.add(WEIGHT_SPOTS_VECTOR);
                }
                if (!pathDocsVec.isEmpty()) {
                    paths.add(pathDocsVec);
                    weights.add(WEIGHT_SPOT_DOCS_VECTOR);
                }
            } else {
                log.warn("embedding_unavailable，跳过向量路（回退双路）");
            }
        }
        lastFusedPathCount = paths.size();
        log.info("rag_recall_done attempted={} fused_paths={}", lastAttemptedPathCount, lastFusedPathCount);

        // 加权 RRF 融合 + credibility 调节；失败降级普通 RRF
        List<Map<String, Object>> fused;
        try {
            fused = Rrf.rrfMergeWithWeights(paths, weights, Rrf.DEFAULT_K, "id",
                credibilityService == null ? null : credibilityService::weightByCredibility);
        } catch (Exception e) {
            log.warn("weighted_rrf_failed，降级普通 RRF error={}", e.getMessage());
            fused = Rrf.rrfMerge(paths, Rrf.DEFAULT_K, "id");
        }
        log.info("rag_rrf_done fused={}", fused.size());

        if (fused.isEmpty()) {
            return List.of();
        }

        // 四路模式：Cross-Encoder 重排（叠加 credibility）；不可用 → 降级 RRF 顺序
        lastReranked = false;
        if (fourWayEnabled && rerankWithCredibility != null) {
            fused = rerankWithCredibility.rerank(query, fused);
            lastReranked = true;
            log.info("rag_rerank_done count={}", fused.size());
        }

        return fused.subList(0, Math.min(targetLimit, fused.size()));
    }

    /** 双路构造默认关闭四路。 */
    public boolean isFourWayEnabled() {
        return fourWayEnabled;
    }

    public int getLastAttemptedPathCount() {
        return lastAttemptedPathCount;
    }

    public int getLastFusedPathCount() {
        return lastFusedPathCount;
    }

    public boolean isLastReranked() {
        return lastReranked;
    }

    public int getLimit() {
        return limit;
    }
}
