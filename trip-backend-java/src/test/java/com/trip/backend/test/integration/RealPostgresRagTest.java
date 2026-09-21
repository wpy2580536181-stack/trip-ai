package com.trip.backend.test.integration;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import com.trip.backend.infra.ai.BgeReranker;
import com.trip.backend.service.rag.CredibilityService;
import com.trip.backend.service.rag.FulltextSearch;
import com.trip.backend.service.rag.QueryRewriter;
import com.trip.backend.service.rag.RatingSearch;
import com.trip.backend.service.rag.RerankWithCredibility;
import com.trip.backend.service.rag.RetrievalPipeline;
import com.trip.backend.service.rag.VectorSearchSpots;
import com.trip.backend.service.rag.VectorSearchSpotDocs;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.sql.Connection;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 真实环境集成测试（需本机 Docker：PostgreSQL localhost:5432/trip_db trip/trip123，
 * 数据 30804 spots / 30794 带 embedding）。
 *
 * 补跑此前 [需真实环境] 的判定：
 * - J-C2 判定 1：双路 top-5 与 Python 对拍（基准由 trip-backend/.venv 实测记录）
 * - J-C2 websearch 成功路径（真实 PG，H2 只能测降级）
 * - J-C3 向量路 SQL 真实执行（CAST(? AS vector) + HNSW）
 * - J-C4 embedding UPDATE SQL 真实执行
 *
 * 跳过条件：PG 不可达时 @BeforeAll 抛 SkipException。
 */
class RealPostgresRagTest {

    private static JdbcTemplate jdbc;
    private static DriverManagerDataSource ds;

    @BeforeAll
    static void connect() {
        ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.postgresql.Driver");
        ds.setUrl("jdbc:postgresql://localhost:5432/trip_db");
        ds.setUsername("trip");
        ds.setPassword("trip123");
        jdbc = new JdbcTemplate(ds);
        jdbc.setQueryTimeout(10);
        try (Connection c = ds.getConnection()) {
            assertTrue(c.isValid(5), "PG 应可达");
        } catch (Exception e) {
            throw new org.opentest4j.TestAbortedException("PG 不可达，跳过真实环境测试: " + e.getMessage());
        }
    }

    @AfterAll
    static void cleanup() {
        // 清理对拍临时数据（按 name 匹配，避免误删真实数据）；服务不可达时静默跳过
        try {
            jdbc.update("DELETE FROM spots WHERE name = '__rag_test_tmp__'");
        } catch (Exception ignored) {
        }
    }

    // ------------------------------------------------------------------
    // J-C2 判定 1：双路 top-5 与 Python 对拍（基准见提交说明）
    // ------------------------------------------------------------------

    private static final String[][] BASELINE = {
        // query, city, category, expected id list（Python .venv 实测 2026-09-21）
        {"天安门", "北京", null, "7136,659,5630,7814,7826"},
        {"故宫", "北京", null, "7144,667,660,7135,7136"},
        {"the", null, null, "15151,32749,5553,12134,12136"},
        {"美食", "成都", "food", "7428,876,7426,872,873"},
        {"博物馆", "上海", null, "4811,5560,6308,7075,600"},
    };

    @Test
    void dualPathTop5MatchesPythonBaseline() {
        RetrievalPipeline pipeline = new RetrievalPipeline(new QueryRewriter(), new RatingSearch(jdbc), new FulltextSearch(jdbc), 5);
        for (String[] row : BASELINE) {
            String query = row[0];
            String city = row[1];
            String category = row[2];
            List<Map<String, Object>> results = pipeline.retrieve(query, city, category, 5);
            List<String> ids = results.stream().map(r -> String.valueOf(r.get("id"))).toList();
            String actual = String.join(",", ids);
            assertEquals(row[3], actual, "top-5 应与 Python 一致: query=" + query + " city=" + city);
        }
    }

    // ------------------------------------------------------------------
    // RatingSearch 真实数据
    // ------------------------------------------------------------------

    @Test
    void ratingSearchRealDataOrdersByRatingDesc() {
        RatingSearch search = new RatingSearch(jdbc);
        List<Map<String, Object>> results = search.search("北京", null, 5);
        assertEquals(5, results.size());
        for (int i = 1; i < results.size(); i++) {
            double prev = (Double) results.get(i - 1).get("rating");
            double cur = (Double) results.get(i).get("rating");
            assertTrue(prev >= cur, "rating 应降序");
        }
        assertTrue(results.stream().allMatch(r -> "北京".equals(r.get("city"))), "全部应为北京");
    }

    // ------------------------------------------------------------------
    // FulltextSearch websearch 成功路径（真实 PG；H2 只能测降级）
    // ------------------------------------------------------------------

    @Test
    void fulltextWebsearchSucceedsOnRealPg() {
        FulltextSearch search = new FulltextSearch(jdbc);
        List<Map<String, Object>> results = search.search(List.of("天安门"), "北京", null, 10);
        assertFalse(results.isEmpty(), "websearch 应命中");
        assertEquals("pg_fulltext", results.get(0).get("_source"), "成功路径 _source=pg_fulltext");
        // 命中的行 name/description 应含查询词或经 chinese 配置分词命中
        assertTrue(results.size() >= 5);
    }

    @Test
    void fulltextWebsearchZeroHitsReturnsEmptyWithoutFallback() {
        // 对齐 Python：websearch 0 命中返回空列表（不触发 LIKE 降级，只有异常才降级）
        FulltextSearch search = new FulltextSearch(jdbc);
        List<Map<String, Object>> results = search.search(List.of("故宫"), "北京", null, 10);
        assertTrue(results.isEmpty(), "simple 分词下 '故宫' websearch 0 命中 → 空（与 Python 一致）");
    }

    // ------------------------------------------------------------------
    // VectorSearchSpots 真实 pgvector + HNSW
    // ------------------------------------------------------------------

    @Test
    void vectorSearchSpotsRealEmbeddingRunsOnPg() {
        // 取一条真实 spot embedding 作为查询向量
        float[] queryVec = fetchEmbedding("SELECT embedding::text FROM spots WHERE embedding IS NOT NULL AND city='北京' LIMIT 1");
        VectorSearchSpots search = new VectorSearchSpots(jdbc);
        List<Map<String, Object>> results = search.search(queryVec, "北京", null, 5);

        assertFalse(results.isEmpty(), "真实 embedding 应命中（HNSW）");
        assertEquals("pgvector", results.get(0).get("_source"));
        // score 应降序且 ∈ [0,1]
        for (int i = 1; i < results.size(); i++) {
            double prev = (Double) results.get(i - 1).get("score");
            double cur = (Double) results.get(i).get("score");
            assertTrue(prev >= cur, "相似度应降序");
        }
        double top = (Double) results.get(0).get("score");
        assertTrue(top > 0 && top <= 1.0000001, "余弦相似度应在 (0,1]：" + top);
    }

    @Test
    void vectorSearchSpotDocsEmptyEmbeddingReturnsEmpty() {
        // spot_docs.embedding 全空 → SQL 正常执行返回空（不抛异常）
        float[] queryVec = fetchEmbedding("SELECT embedding::text FROM spots WHERE embedding IS NOT NULL LIMIT 1");
        VectorSearchSpotDocs search = new VectorSearchSpotDocs(jdbc);
        List<Map<String, Object>> results = search.search(queryVec, null, 10);
        assertTrue(results.isEmpty(), "spot_docs embedding 全空 → 空结果");
    }

    // ------------------------------------------------------------------
    // J-C4 embedding UPDATE SQL 真实执行
    // ------------------------------------------------------------------

    @Test
    void embeddingSyncSqlUpdatesRealPg() throws Exception {
        // 插入临时 spot（真实 schema：description/tags not null）
        jdbc.update("INSERT INTO spots (name, city, category, description, tags, created_at) "
            + "VALUES ('__rag_test_tmp__', '北京', 'attraction', '临时对拍数据', '{}', now())");
        Long tmpId = jdbc.queryForObject(
            "SELECT id FROM spots WHERE name = '__rag_test_tmp__' ORDER BY id DESC LIMIT 1", Long.class);
        assertTrue(tmpId != null, "临时 spot 应已插入");

        float[] vec = new float[512];
        for (int i = 0; i < 512; i++) {
            vec[i] = 0.001f * i;
        }
        String pgVec = VectorSearchSpots.toPgVectorString(vec);
        int updated = jdbc.update("UPDATE spots SET embedding = CAST(? AS vector) WHERE id = ?", pgVec, tmpId);
        assertEquals(1, updated, "embedding 写入应成功");

        String stored = jdbc.queryForObject("SELECT embedding::text FROM spots WHERE id = ?", String.class, tmpId);
        assertTrue(stored != null && stored.startsWith("[") && stored.endsWith("]"),
            "embedding 应已持久化: " + (stored == null ? "null" : stored.substring(0, Math.min(30, stored.length()))));
        String[] storedParts = stored.substring(1, stored.length() - 1).split(",");
        assertEquals(512, storedParts.length, "持久化向量应为 512 维");

        jdbc.update("DELETE FROM spots WHERE id = ?", tmpId);
    }

    // ------------------------------------------------------------------
    // J-C3 四路融合：向量路真实参与（真实 spot embedding 作查询向量）
    // ------------------------------------------------------------------

    @Test
    void fourWayFusionWithRealVectorPath() {
        // 用真实 spot embedding 构造查询向量（embedder 侧验证 [需真实环境]；融合/向量 SQL 本机可证）
        float[] queryVec = fetchEmbedding("SELECT embedding::text FROM spots WHERE embedding IS NOT NULL AND city='北京' LIMIT 1");
        BgeEmbedder fakeEmbedder = new BgeEmbedder(new EmbedderHealth(), new OnnxModelLoader(), "models/x", 512) {
            @Override
            public java.util.Optional<float[]> embed(String text) {
                return java.util.Optional.of(queryVec);
            }
        };

        CredibilityService credibility = new CredibilityService();
        RetrievalPipeline pipeline = new RetrievalPipeline(
            new QueryRewriter(), new RatingSearch(jdbc), new FulltextSearch(jdbc),
            fakeEmbedder, new VectorSearchSpots(jdbc), new VectorSearchSpotDocs(jdbc),
            credibility,
            new RerankWithCredibility(new BgeReranker(new OnnxModelLoader(), "models/bge-reranker-base", 512), 0.3),
            true, 5);

        List<Map<String, Object>> results = pipeline.retrieve("北京 故宫", "北京", null, 5);
        assertEquals(4, pipeline.getLastAttemptedPathCount(), "四路尝试");
        // 真实 PG：fulltext + rating + spots_vector 有结果；spot_docs embedding 全空 → 空
        assertTrue(pipeline.getLastFusedPathCount() >= 3, "向量路应真实参与融合: " + pipeline.getLastFusedPathCount());
        assertEquals(5, results.size(), "四路融合后应出 top-5");
        assertTrue(results.get(0).containsKey("_rrf_score"));
        // 向量路结果的 _source 应包含 pgvector 来源
        assertTrue(results.stream().anyMatch(r -> "pgvector".equals(r.get("_source"))),
            "top-5 中应含 pgvector 召回: " + results.stream().map(r -> String.valueOf(r.get("_source"))).toList());
    }

    private float[] fetchEmbedding(String sql) {
        String vecText = jdbc.queryForObject(sql, String.class);
        assertTrue(vecText != null && vecText.startsWith("["));
        String[] parts = vecText.substring(1, vecText.length() - 1).split(",");
        float[] vec = new float[parts.length];
        for (int i = 0; i < parts.length; i++) {
            vec[i] = Float.parseFloat(parts[i].trim());
        }
        return vec;
    }
}
