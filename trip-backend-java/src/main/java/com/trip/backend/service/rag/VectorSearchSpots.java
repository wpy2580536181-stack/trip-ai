package com.trip.backend.service.rag;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * pgvector 向量检索 spots 表（对应 Python src/services/rag/vector_search.py vector_search_spots）。
 *
 * 使用原生 SQL 利用 pgvector 操作符 <=>（余弦距离）：score = 1 - cosine_distance。
 * 失败 → 返回空（由管线跳过向量路，不抛异常）。
 */
@Component
public class VectorSearchSpots {

    private static final Logger log = LoggerFactory.getLogger(VectorSearchSpots.class);

    private final JdbcTemplate jdbcTemplate;

    public VectorSearchSpots(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * pgvector 余弦相似度检索 spots。
     *
     * @param queryEmbedding 查询向量（512 维）
     * @param city           城市过滤（可空）
     * @param category       类型过滤（可空）
     * @param limit          返回数量
     * @return 结果列表（score=余弦相似度 0~1，_source=pgvector）；失败返回空
     */
    public List<Map<String, Object>> search(float[] queryEmbedding, String city, String category, int limit) {
        if (queryEmbedding == null || queryEmbedding.length == 0) {
            return List.of();
        }
        String vec = toPgVectorString(queryEmbedding);
        StringBuilder sql = new StringBuilder(
            "SELECT id, name, city, category, description, rating, tags, avg_cost, "
                + "1 - (embedding <=> CAST(? AS vector)) AS score FROM spots WHERE embedding IS NOT NULL");
        List<Object> params = new ArrayList<>();
        params.add(vec);
        if (city != null && !city.isBlank()) {
            sql.append(" AND city = ?");
            params.add(city);
        }
        if (category != null && !category.isBlank()) {
            sql.append(" AND category = ?");
            params.add(category);
        }
        sql.append(" ORDER BY embedding <=> CAST(? AS vector) LIMIT ?");
        params.add(vec);
        params.add(limit);

        try {
            List<Map<String, Object>> rows = jdbcTemplate.query(sql.toString(), this::mapRow, params.toArray());
            for (Map<String, Object> row : rows) {
                row.put("_source", "pgvector");
            }
            return rows;
        } catch (Exception e) {
            log.warn("pgvector_spots_search_failed（跳过向量路） error={}", e.getMessage());
            return List.of();
        }
    }

    private Map<String, Object> mapRow(ResultSet rs, int rowNum) throws SQLException {
        Map<String, Object> spot = new LinkedHashMap<>();
        spot.put("id", String.valueOf(rs.getLong("id")));
        spot.put("name", rs.getString("name"));
        spot.put("city", rs.getString("city"));
        spot.put("category", rs.getString("category"));
        spot.put("description", rs.getString("description"));
        double rating = rs.getDouble("rating");
        spot.put("rating", rs.wasNull() ? 0 : rating);
        spot.put("tags", rs.getString("tags"));
        int avgCost = rs.getInt("avg_cost");
        spot.put("avg_cost", rs.wasNull() ? null : avgCost);
        spot.put("score", rs.getDouble("score"));
        return spot;
    }

    /** float[] → pgvector vector 文本 "[0.1,0.2,...]"。 */
    public static String toPgVectorString(float[] embedding) {
        StringBuilder sb = new StringBuilder(embedding.length * 8 + 2);
        sb.append('[');
        for (int i = 0; i < embedding.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(embedding[i]);
        }
        sb.append(']');
        return sb.toString();
    }
}
