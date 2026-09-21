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
 * 评分排序检索（对应 Python KnowledgeService._rating_search）。
 *
 * `SELECT ... FROM spots [WHERE city=? AND category=?] ORDER BY rating DESC NULLS LAST LIMIT ?`
 */
@Component
public class RatingSearch {

    private static final Logger log = LoggerFactory.getLogger(RatingSearch.class);

    private final JdbcTemplate jdbcTemplate;

    public RatingSearch(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * 按评分降序召回 spots。
     *
     * @param city     城市过滤（可空）
     * @param category 类型过滤（可空）
     * @param limit    返回数量
     */
    public List<Map<String, Object>> search(String city, String category, int limit) {
        StringBuilder sql = new StringBuilder(
            "SELECT id, name, city, category, description, rating, tags, avg_cost FROM spots");
        List<String> clauses = new ArrayList<>();
        List<Object> params = new ArrayList<>();
        if (city != null && !city.isBlank()) {
            clauses.add("city = ?");
            params.add(city);
        }
        if (category != null && !category.isBlank()) {
            clauses.add("category = ?");
            params.add(category);
        }
        if (!clauses.isEmpty()) {
            sql.append(" WHERE ").append(String.join(" AND ", clauses));
        }
        sql.append(" ORDER BY rating DESC NULLS LAST LIMIT ?");
        params.add(limit);

        try {
            return jdbcTemplate.query(sql.toString(), this::mapRow, params.toArray());
        } catch (Exception e) {
            log.error("rating_search_failed city={} category={} error={}", city, category, e.getMessage());
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
        spot.put("_source", "rating");
        return spot;
    }
}
