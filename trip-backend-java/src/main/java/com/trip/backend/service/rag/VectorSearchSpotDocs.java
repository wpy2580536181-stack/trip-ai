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
 * pgvector 向量检索 spot_docs 表（文本层向量召回，对应 Python vector_search_spot_docs
 * + KnowledgeService._aggregate_spot_docs）。
 *
 * 文档块级命中聚合到 spot 级：同 spot 取 score 最高的 max_chunks=3 块拼进 evidence，
 * 携带 credibility_score 与来源信息，供 RRF 调节与重排使用。
 * 失败 → 返回空（由管线跳过向量路，不抛异常）。
 */
@Component
public class VectorSearchSpotDocs {

    private static final Logger log = LoggerFactory.getLogger(VectorSearchSpotDocs.class);

    private static final int MAX_CHUNKS = 3;

    private final JdbcTemplate jdbcTemplate;

    public VectorSearchSpotDocs(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * pgvector 检索 spot_docs 并聚合到 spot 级。
     *
     * @param queryEmbedding 查询向量（512 维）
     * @param city           城市过滤（可空，JOIN spots）
     * @param limit          返回块数
     * @return spot 级结果（_source=spot_docs，含 credibility_score/evidence）；失败返回空
     */
    public List<Map<String, Object>> search(float[] queryEmbedding, String city, int limit) {
        if (queryEmbedding == null || queryEmbedding.length == 0) {
            return List.of();
        }
        String vec = VectorSearchSpots.toPgVectorString(queryEmbedding);
        StringBuilder sql = new StringBuilder(
            "SELECT sd.id, sd.spot_id, sd.source_type, sd.source_name, sd.source_url, "
                + "sd.content, sd.credibility_score, "
                + "1 - (sd.embedding <=> CAST(? AS vector)) AS score FROM spot_docs sd");
        List<Object> params = new ArrayList<>();
        params.add(vec);
        if (city != null && !city.isBlank()) {
            sql.append(" JOIN spots s ON sd.spot_id = s.id");
            sql.append(" WHERE sd.embedding IS NOT NULL AND s.city = ?");
            params.add(city);
        } else {
            sql.append(" WHERE sd.embedding IS NOT NULL");
        }
        sql.append(" ORDER BY sd.embedding <=> CAST(? AS vector) LIMIT ?");
        params.add(vec);
        params.add(limit);

        try {
            List<Map<String, Object>> hits = jdbcTemplate.query(sql.toString(), this::mapRow, params.toArray());
            return aggregateToSpot(hits);
        } catch (Exception e) {
            log.warn("pgvector_spot_docs_search_failed（跳过向量路） error={}", e.getMessage());
            return List.of();
        }
    }

    private Map<String, Object> mapRow(ResultSet rs, int rowNum) throws SQLException {
        Map<String, Object> hit = new LinkedHashMap<>();
        hit.put("spot_id", String.valueOf(rs.getLong("spot_id")));
        hit.put("source_type", rs.getString("source_type"));
        hit.put("source_name", rs.getString("source_name"));
        hit.put("source_url", rs.getString("source_url"));
        hit.put("content", rs.getString("content"));
        double cred = rs.getDouble("credibility_score");
        hit.put("credibility_score", rs.wasNull() ? 0.5 : cred);
        hit.put("score", rs.getDouble("score"));
        return hit;
    }

    /**
     * 把 chunk 级命中聚合为 spot 级结果（对应 Python _aggregate_spot_docs，max_chunks=3）。
     */
    static List<Map<String, Object>> aggregateToSpot(List<Map<String, Object>> hits) {
        Map<String, List<Map<String, Object>>> groups = new LinkedHashMap<>();
        for (Map<String, Object> h : hits) {
            Object sid = h.get("spot_id");
            if (sid == null) {
                continue;
            }
            groups.computeIfAbsent(String.valueOf(sid), k -> new ArrayList<>()).add(h);
        }

        List<Map<String, Object>> out = new ArrayList<>();
        for (Map.Entry<String, List<Map<String, Object>>> entry : groups.entrySet()) {
            String sid = entry.getKey();
            List<Map<String, Object>> chunkHits = entry.getValue();
            chunkHits.sort((a, b) -> Double.compare((Double) b.get("score"), (Double) a.get("score")));
            List<Map<String, Object>> top = chunkHits.subList(0, Math.min(MAX_CHUNKS, chunkHits.size()));
            Map<String, Object> best = top.get(0);

            List<Map<String, Object>> evChunks = new ArrayList<>();
            for (Map<String, Object> c : top) {
                Map<String, Object> chunk = new LinkedHashMap<>();
                chunk.put("content", c.get("content"));
                chunk.put("credibility_score", c.get("credibility_score"));
                evChunks.add(chunk);
            }

            Map<String, Object> evidence = new LinkedHashMap<>();
            evidence.put("source_type", best.get("source_type"));
            evidence.put("source_name", best.get("source_name"));
            evidence.put("source_url", best.get("source_url"));
            evidence.put("content", joinContents(top));
            evidence.put("chunks", evChunks);
            evidence.put("credibility_score", best.get("credibility_score"));

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("id", sid);
            item.put("name", "");
            item.put("city", "");
            item.put("category", "");
            item.put("rating", 0);
            item.put("score", best.getOrDefault("score", 0.5));
            item.put("_source", "spot_docs");
            item.put("source_type", best.get("source_type"));
            item.put("source_name", best.get("source_name"));
            item.put("source_url", best.get("source_url"));
            item.put("credibility_score", best.get("credibility_score"));
            item.put("evidence", evidence);
            out.add(item);
        }
        return out;
    }

    private static String joinContents(List<Map<String, Object>> top) {
        StringBuilder sb = new StringBuilder();
        for (Map<String, Object> c : top) {
            if (sb.length() > 0) {
                sb.append('\n');
            }
            Object content = c.get("content");
            sb.append(content == null ? "" : content);
        }
        return sb.toString();
    }
}
