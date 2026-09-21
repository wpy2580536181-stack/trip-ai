package com.trip.backend.test.unit;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.BgeReranker;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import com.trip.backend.service.rag.CredibilityService;
import com.trip.backend.service.rag.FulltextSearch;
import com.trip.backend.service.rag.QueryRewriter;
import com.trip.backend.service.rag.RatingSearch;
import com.trip.backend.service.rag.RerankWithCredibility;
import com.trip.backend.service.rag.RetrievalPipeline;
import com.trip.backend.service.rag.VectorSearchSpots;
import com.trip.backend.service.rag.VectorSearchSpotDocs;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C3 四路召回开关 + 降级回退测试（H2 内存库）。
 *
 * - 判定 1：开关关闭 attempted=2（双路）、开启 attempted=4（四路尝试）
 * - 判定 3：embedding 不可用 / 向量 SQL 失败（H2 无 pgvector）→ 自动回退双路，检索仍可用
 * - VectorSearchSpots / VectorSearchSpotDocs 在无 pgvector 的库上失败返回空（不抛异常）
 *
 * [需真实环境]：判定 2（四路 Hit@K/MRR ≥ 双路基线）需 PostgreSQL + ONNX 模型，
 * 本机不可执行，已标注待真实环境验证。
 */
class PipelineFourWayTest {

    private static JdbcTemplate jdbc;
    private static CredibilityService credibility;

    @BeforeAll
    static void setupDb() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:fourwaydb;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE");
        ds.setUsername("sa");
        ds.setPassword("");
        jdbc = new JdbcTemplate(ds);
        credibility = new CredibilityService();

        jdbc.execute("""
            CREATE TABLE spots (
                id BIGINT PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                city VARCHAR(100) NOT NULL,
                category VARCHAR(100) NOT NULL,
                description TEXT,
                tags CLOB,
                avg_cost INTEGER,
                rating DOUBLE,
                created_at TIMESTAMP
            )
            """);
        jdbc.execute("""
            CREATE TABLE spot_docs (
                id BIGINT PRIMARY KEY,
                spot_id BIGINT NOT NULL,
                source_type VARCHAR(50),
                source_name VARCHAR(200),
                source_url VARCHAR(500),
                title VARCHAR(500),
                content TEXT,
                chunk_index INTEGER,
                credibility_score DOUBLE,
                retrieved_at TIMESTAMP
            )
            """);
    }

    @BeforeEach
    void seedData() {
        jdbc.update("DELETE FROM spots");
        jdbc.update("DELETE FROM spot_docs");
        jdbc.update("INSERT INTO spots (id,name,city,category,description,rating) VALUES (1,'北京故宫博物院','北京','attraction','故宫历史建筑',4.8)");
        jdbc.update("INSERT INTO spots (id,name,city,category,description,rating) VALUES (2,'北京长城','北京','attraction','长城风光',4.9)");
        jdbc.update("INSERT INTO spots (id,name,city,category,description,rating) VALUES (3,'北京烤鸭','北京','food','全聚德烤鸭',4.6)");
        jdbc.update("INSERT INTO spot_docs (id,spot_id,source_type,source_name,source_url,title,content,chunk_index,credibility_score) "
            + "VALUES (10,1,'wiki','维基百科','https://zh.wikipedia.org/wiki/故宫','故宫','紫禁城历史与建筑',0,0.95)");
        jdbc.update("INSERT INTO spot_docs (id,spot_id,source_type,source_name,source_url,title,content,chunk_index,credibility_score) "
            + "VALUES (11,1,'ugc_public','小红书','https://xhs.example.com/1','故宫游记','游客故宫游玩体验',0,0.5)");
    }

    private RetrievalPipeline dualPipeline() {
        return new RetrievalPipeline(new QueryRewriter(), new RatingSearch(jdbc), new FulltextSearch(jdbc), 5);
    }

    private RetrievalPipeline fourWayPipeline(BgeEmbedder embedder) {
        VectorSearchSpots vectorSpots = new VectorSearchSpots(jdbc);
        VectorSearchSpotDocs vectorDocs = new VectorSearchSpotDocs(jdbc);
        RerankWithCredibility rerank = new RerankWithCredibility(
            new BgeReranker(new OnnxModelLoader(), "models/bge-reranker-base", 512), 0.3);
        return new RetrievalPipeline(
            new QueryRewriter(), new RatingSearch(jdbc), new FulltextSearch(jdbc),
            embedder, vectorSpots, vectorDocs, credibility, rerank, true, 5);
    }

    // ------------------------------------------------------------------
    // 判定 1：开关关闭走双路 / 开启走四路（计数可证）
    // ------------------------------------------------------------------

    @Test
    void fourWayDisabledRunsDualPath() {
        RetrievalPipeline pipeline = dualPipeline();
        List<Map<String, Object>> results = pipeline.retrieve("故宫", "北京", null, 5);

        assertEquals(2, pipeline.getLastAttemptedPathCount(), "开关关闭 → 尝试 2 条路径");
        assertEquals(2, pipeline.getLastFusedPathCount());
        assertFalse(pipeline.isLastReranked(), "双路模式不启用 Cross-Encoder 重排");
        assertFalse(results.isEmpty(), "双路仍出结果");
    }

    @Test
    void fourWayEnabledAttemptsFourPaths() {
        // embedding 未预热（不可用）→ 仍尝试四路（attempted=4），向量路被跳过
        EmbedderHealth health = new EmbedderHealth();
        BgeEmbedder embedder = new BgeEmbedder(health, new OnnxModelLoader(), "models/bge-small-zh-v1.5", 512);
        RetrievalPipeline pipeline = fourWayPipeline(embedder);

        List<Map<String, Object>> results = pipeline.retrieve("故宫", "北京", null, 5);

        assertEquals(4, pipeline.getLastAttemptedPathCount(), "开关开启 → 尝试 4 条路径");
        assertTrue(pipeline.isLastReranked(), "四路模式启用重排");
    }

    // ------------------------------------------------------------------
    // 判定 3：embedding 故障 / 向量 SQL 失败 → 自动回退双路，检索仍可用
    // ------------------------------------------------------------------

    @Test
    void fourWayFallsBackToDualWhenEmbeddingUnavailable() {
        // embedding 未预热 → embed 返回 empty → 跳过向量路
        EmbedderHealth health = new EmbedderHealth();
        BgeEmbedder embedder = new BgeEmbedder(health, new OnnxModelLoader(), "models/bge-small-zh-v1.5", 512);
        RetrievalPipeline pipeline = fourWayPipeline(embedder);

        List<Map<String, Object>> results = pipeline.retrieve("故宫", "北京", null, 5);

        assertEquals(2, pipeline.getLastFusedPathCount(), "向量路被跳过 → 融合 2 条路径（回退双路）");
        assertFalse(results.isEmpty(), "回退双路后检索仍可用");
        // 重排降级：reranker 不可用 → 按 credibility 排序；故宫(spot1) 有 wiki cred 0.95
        assertEquals("1", results.get(0).get("id"));
    }

    @Test
    void vectorSearchFailsGracefullyWithoutPgvector() {
        // H2 无 pgvector <=> 操作符 → 失败返回空（不抛异常）
        VectorSearchSpots vectorSpots = new VectorSearchSpots(jdbc);
        VectorSearchSpotDocs vectorDocs = new VectorSearchSpotDocs(jdbc);
        float[] vec = new float[4];
        vec[0] = 0.1f;
        vec[1] = 0.2f;

        assertTrue(vectorSpots.search(vec, "北京", null, 10).isEmpty(), "无 pgvector → 返回空（跳过向量路）");
        assertTrue(vectorDocs.search(vec, "北京", 10).isEmpty());
    }

    @Test
    void pgVectorStringFormatMatchesPython() {
        // Python: str([0.1, 0.2]) -> "[0.1, 0.2]"；pgvector 接受无空格 "[0.1,0.2]"
        float[] vec = {0.1f, 0.2f, 0.3f};
        assertEquals("[0.1,0.2,0.3]", VectorSearchSpots.toPgVectorString(vec));
    }
}
