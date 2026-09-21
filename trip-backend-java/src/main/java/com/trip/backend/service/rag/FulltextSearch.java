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
 * PostgreSQL 全文检索 spots 表（对应 Python src/services/rag/fulltext_search.py）。
 *
 * - 首选：websearch_to_tsquery('chinese', :q) + tsvector 匹配（zhparser）
 * - 失败降级：LIKE 模糊匹配（name/description OR 组合），_source="pg_like"
 */
@Component
public class FulltextSearch {

    private static final Logger log = LoggerFactory.getLogger(FulltextSearch.class);

    private final JdbcTemplate jdbcTemplate;

    public FulltextSearch(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * 全文检索 spots（失败自动降级 LIKE）。
     *
     * @param keywords 关键词列表（对应 Python 传原始 query 单元素列表）
     * @param city     城市过滤（可空）
     * @param category 类型过滤（可空）
     * @param limit    返回数量
     */
    public List<Map<String, Object>> search(List<String> keywords, String city, String category, int limit) {
        if (keywords == null || keywords.isEmpty()) {
            return List.of();
        }
        try {
            return websearchSearch(keywords, city, category, limit);
        } catch (Exception e) {
            log.warn("pg_fulltext_failed，降级 LIKE 检索 error={}", e.getMessage());
            return likeSearch(keywords, city, category, limit);
        }
    }

    /** websearch_to_tsquery 全文检索（zhparser）。失败抛异常 → 上层降级。 */
    private List<Map<String, Object>> websearchSearch(List<String> keywords, String city, String category, int limit) {
        String searchText = String.join(" ", keywords);
        StringBuilder sql = new StringBuilder(
            "SELECT id, name, city, category, description, rating, tags, avg_cost FROM spots WHERE "
                + "to_tsvector('chinese', coalesce(name, '') || ' ' || coalesce(description, '')) "
                + "@@ websearch_to_tsquery('chinese', ?)");
        List<Object> params = new ArrayList<>();
        params.add(searchText);

        if (city != null && !city.isBlank()) {
            sql.append(" AND city = ?");
            params.add(city);
        }
        if (category != null && !category.isBlank()) {
            sql.append(" AND category = ?");
            params.add(category);
        }
        sql.append(" ORDER BY rating DESC NULLS LAST LIMIT ?");
        params.add(limit);

        List<Map<String, Object>> rows = jdbcTemplate.query(sql.toString(), this::mapRow, params.toArray());
        for (Map<String, Object> row : rows) {
            row.put("_source", "pg_fulltext");
        }
        return rows;
    }

    /** LIKE 降级检索：name/description 任一关键词命中（OR 组合）。 */
    private List<Map<String, Object>> likeSearch(List<String> keywords, String city, String category, int limit) {
        try {
            StringBuilder sql = new StringBuilder("SELECT id, name, city, category, description, rating, tags, avg_cost FROM spots WHERE ");
            List<String> orConds = new ArrayList<>();
            List<Object> params = new ArrayList<>();
            for (String kw : keywords) {
                orConds.add("(name LIKE ? OR description LIKE ?)");
                params.add("%" + kw + "%");
                params.add("%" + kw + "%");
            }
            sql.append(String.join(" OR ", orConds));
            if (city != null && !city.isBlank()) {
                sql.append(" AND city = ?");
                params.add(city);
            }
            if (category != null && !category.isBlank()) {
                sql.append(" AND category = ?");
                params.add(category);
            }
            sql.append(" ORDER BY rating DESC NULLS LAST LIMIT ?");
            params.add(limit);

            List<Map<String, Object>> rows = jdbcTemplate.query(sql.toString(), this::mapRow, params.toArray());
            for (Map<String, Object> row : rows) {
                row.put("_source", "pg_like");
            }
            return rows;
        } catch (Exception e) {
            log.error("pg_like_search_failed error={}", e.getMessage());
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
        return spot;
    }
}
