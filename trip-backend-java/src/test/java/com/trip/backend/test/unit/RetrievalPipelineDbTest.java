package com.trip.backend.test.unit;

import com.trip.backend.service.rag.FulltextSearch;
import com.trip.backend.service.rag.QueryRewriter;
import com.trip.backend.service.rag.RatingSearch;
import com.trip.backend.service.rag.RetrievalPipeline;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C2 双路检索流水线 DB 测试（H2 内存库，PostgreSQL 兼容模式）。
 *
 * - rating 路：ORDER BY rating DESC NULLS LAST + city/category 过滤
 * - pg_fulltext 路：H2 无 websearch_to_tsquery → 自动降级 LIKE（判定 2），_source=pg_like
 * - RetrievalPipeline：rating + fulltext 双路 → 加权 RRF（0.7/0.5, k=60）→ top-N
 *
 * [需真实环境]：判定 1（与 Python top-5 对拍）、websearch 成功路径需 PostgreSQL
 * （zhparser + websearch_to_tsquery），本机无 PG，websearch 成功路径待真实环境验证；
 * 降级路径（判定 2）与融合排序已在本测试中用 H2 验证。
 */
class RetrievalPipelineDbTest {

    private static JdbcTemplate jdbc;

    @BeforeAll
    static void setupDb() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:ragdb;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=TRUE");
        ds.setUsername("sa");
        ds.setPassword("");
        jdbc = new JdbcTemplate(ds);

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
    }

    @AfterAll
    static void tearDownDb() {
        // DB_CLOSE_DELAY=-1 的内存库随 JVM 退出清理
    }

    @BeforeEach
    void seedData() {
        jdbc.update("DELETE FROM spots");
        insert(1L, "北京故宫博物院", "北京", "attraction", "故宫的历史建筑群，明清皇家宫殿", 4.8, 60);
        insert(2L, "北京长城", "北京", "attraction", "八达岭长城风光", 4.9, 40);
        insert(3L, "北京烤鸭", "北京", "food", "全聚德挂炉烤鸭", 4.6, 200);
        insert(4L, "上海外滩", "上海", "attraction", "外滩江景与万国建筑", 4.7, null);
        insert(5L, "北京胡同游", "北京", "attraction", "老北京胡同文化体验", 4.5, 80);
        insert(6L, "故宫文创雪糕", "北京", "food", "故宫主题文创雪糕", 4.4, 25);
    }

    private void insert(long id, String name, String city, String category, String desc, double rating, Integer avgCost) {
        jdbc.update("INSERT INTO spots (id, name, city, category, description, tags, avg_cost, rating) VALUES (?,?,?,?,?,?,?,?)",
            id, name, city, category, desc, null, avgCost, rating);
    }

    // ------------------------------------------------------------------
    // RatingSearch
    // ------------------------------------------------------------------

    @Test
    void ratingSearchOrdersByRatingDesc() {
        RatingSearch search = new RatingSearch(jdbc);
        List<Map<String, Object>> results = search.search("北京", null, 5);

        assertEquals(5, results.size());
        // 北京 5 条按 rating 降序：长城4.9, 故宫4.8, 烤鸭4.6, 胡同4.5, 雪糕4.4
        assertEquals(List.of("2", "1", "3", "5", "6"), ids(results));
        assertEquals("rating", results.get(0).get("_source"));
        assertEquals(4.9, (Double) results.get(0).get("rating"), 1e-9);
    }

    @Test
    void ratingSearchFiltersCityAndCategory() {
        RatingSearch search = new RatingSearch(jdbc);
        List<Map<String, Object>> results = search.search("北京", "attraction", 10);
        assertEquals(List.of("2", "1", "5"), ids(results));

        List<Map<String, Object>> shanghai = search.search("上海", null, 10);
        assertEquals(List.of("4"), ids(shanghai));
    }

    @Test
    void ratingSearchHandlesNullRatingLast() {
        // 新增 rating=NULL 记录 → NULLS LAST
        jdbc.update("INSERT INTO spots (id, name, city, category, description, rating) VALUES (7,?,?,?,?,NULL)",
            "北京夜市", "北京", "food", "深夜小吃街");
        RatingSearch search = new RatingSearch(jdbc);
        List<Map<String, Object>> results = search.search("北京", null, 10);
        assertEquals(6, results.size());
        assertEquals("7", results.get(results.size() - 1).get("id"), "NULL rating 应排在最后");
        assertEquals(0, (Double) results.get(results.size() - 1).get("rating"), 1e-9, "NULL rating 映射为 0");
    }

    // ------------------------------------------------------------------
    // FulltextSearch（判定 2：全文失败 → LIKE 降级）
    // ------------------------------------------------------------------

    @Test
    void fulltextSearchDegradesToLikeWhenWebsearchUnavailable() {
        FulltextSearch search = new FulltextSearch(jdbc);
        // H2 无 websearch_to_tsquery → SQL 异常 → 自动降级 LIKE
        List<Map<String, Object>> results = search.search(List.of("故宫"), "北京", null, 10);

        // LIKE 命中 name/description 含"故宫"：[1(故宫博物院/故宫的历史), 6(故宫文创/故宫主题)]
        assertEquals(List.of("1", "6"), ids(results), "降级 LIKE 应按 rating 排序");
        assertEquals("pg_like", results.get(0).get("_source"));
    }

    @Test
    void fulltextSearchLikeFiltersCityAndCategory() {
        FulltextSearch search = new FulltextSearch(jdbc);
        List<Map<String, Object>> results = search.search(List.of("故宫"), "北京", "food", 10);
        assertEquals(List.of("6"), ids(results));
    }

    @Test
    void fulltextSearchEmptyKeywordsReturnsEmpty() {
        FulltextSearch search = new FulltextSearch(jdbc);
        assertTrue(search.search(List.of(), "北京", null, 10).isEmpty());
    }

    // ------------------------------------------------------------------
    // RetrievalPipeline（双路 + 加权 RRF）
    // ------------------------------------------------------------------

    @Test
    void pipelineMergesBothPathsWithWeightedRrf() {
        QueryRewriter rewriter = new QueryRewriter();
        FulltextSearch fulltextSearch = new FulltextSearch(jdbc);
        RatingSearch ratingSearch = new RatingSearch(jdbc);
        RetrievalPipeline pipeline = new RetrievalPipeline(rewriter, ratingSearch, fulltextSearch, 5);

        // query=故宫：fulltext(LIKE) → [1,6]；rating(北京) → [2,1,3,5,6]
        // 加权 RRF(k=60): id1=0.7/60+0.5/61≈0.01986 > id6=0.7/61+0.5/64≈0.01929 > 其余仅 rating
        List<Map<String, Object>> results = pipeline.retrieve("故宫", "北京", null, 5);

        assertEquals(5, results.size());
        assertEquals(List.of("1", "6", "2", "3", "5"), ids(results));
        assertTrue((Double) results.get(0).get("_rrf_score") > (Double) results.get(1).get("_rrf_score"));
    }

    @Test
    void pipelineWithoutCityStillReturnsResults() {
        QueryRewriter rewriter = new QueryRewriter();
        FulltextSearch fulltextSearch = new FulltextSearch(jdbc);
        RatingSearch ratingSearch = new RatingSearch(jdbc);
        RetrievalPipeline pipeline = new RetrievalPipeline(rewriter, ratingSearch, fulltextSearch, 5);

        List<Map<String, Object>> results = pipeline.retrieve("故宫", null, null, 5);
        // 全文路命中 [1,6]；rating 路全量 6 条 → 融合后 top-5
        assertEquals(5, results.size());
        assertEquals("1", results.get(0).get("id"));
        assertEquals("6", results.get(1).get("id"));
    }

    @Test
    void pipelineLimitRespected() {
        QueryRewriter rewriter = new QueryRewriter();
        FulltextSearch fulltextSearch = new FulltextSearch(jdbc);
        RatingSearch ratingSearch = new RatingSearch(jdbc);
        RetrievalPipeline pipeline = new RetrievalPipeline(rewriter, ratingSearch, fulltextSearch, 2);

        List<Map<String, Object>> results = pipeline.retrieve("故宫", "北京", null, 2);
        assertEquals(2, results.size());
        assertEquals(List.of("1", "6"), ids(results));
    }

    private List<String> ids(List<Map<String, Object>> results) {
        return results.stream().map(r -> String.valueOf(r.get("id"))).toList();
    }
}
