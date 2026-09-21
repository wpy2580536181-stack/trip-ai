package com.trip.backend.service.rag;

import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 可信度评分（元信息层，对应 Python src/services/rag/credibility.py）。
 *
 * 为每条文本层文档（SpotDoc）计算 5 维可信度：
 * authority / freshness / agreement / citation / evidence
 * 合成 credibility_score，用于 RRF 融合与 Cross-Encoder 重排阶段对权威源加权。
 *
 * credibility_score = 0.35*authority + 0.20*freshness + 0.20*agreement
 *                     + 0.15*citation + 0.10*evidence
 */
@Component
public class CredibilityService {

    /** source_type -> 权威度默认值（与 Python AUTHORITY_DEFAULTS 一致）。 */
    public static final Map<String, Double> AUTHORITY_DEFAULTS = Map.ofEntries(
        Map.entry("wiki", 1.0),
        Map.entry("wikidata", 1.0),
        Map.entry("official_gov", 1.0),
        Map.entry("official_scenic", 0.9),
        Map.entry("gaode_detail", 0.85),
        Map.entry("api_partner", 0.8),
        Map.entry("osm", 0.85),
        Map.entry("geonames", 0.85),
        Map.entry("academic", 0.95),
        Map.entry("ugc_authorized", 0.6),
        Map.entry("ugc_public", 0.5),
        Map.entry("llm_generated", 0.4),
        Map.entry("realtime_mcp", 0.8)
    );

    /** 5 维权重。 */
    public static final Map<String, Double> WEIGHTS = Map.ofEntries(
        Map.entry("authority", 0.35),
        Map.entry("freshness", 0.20),
        Map.entry("agreement", 0.20),
        Map.entry("citation", 0.15),
        Map.entry("evidence", 0.10)
    );

    /** 引用数归一化分母。 */
    public static final double CITATION_NORM_DENOMINATOR = 50.0;

    /** 新鲜度：距今 ≤30 天视为 1.0。 */
    public static final int FRESHNESS_FULL_DAYS = 30;

    /** 新鲜度：距今 ≥365 天衰减到 0。 */
    public static final int FRESHNESS_ZERO_DAYS = 365;

    /**
     * 由发布时间计算新鲜度（0~1）。
     *
     * @param publishedAt 发布时间（可空 → 0.5）
     * @param now         当前时间（测试可注入）
     */
    public double freshnessFromDate(OffsetDateTime publishedAt, OffsetDateTime now) {
        if (publishedAt == null) {
            return 0.5;
        }
        OffsetDateTime base = now != null ? now : OffsetDateTime.now(ZoneOffset.UTC);
        OffsetDateTime pub = publishedAt.withOffsetSameInstant(ZoneOffset.UTC);
        long days = Math.abs(Duration.between(pub, base).toDays());
        if (days <= FRESHNESS_FULL_DAYS) {
            return 1.0;
        }
        if (days >= FRESHNESS_ZERO_DAYS) {
            return 0.0;
        }
        return round4(1.0 - (double) (days - FRESHNESS_FULL_DAYS) / (FRESHNESS_ZERO_DAYS - FRESHNESS_FULL_DAYS));
    }

    /**
     * 计算单条文本层的 5 维可信度与综合分（对齐 Python compute_credibility）。
     *
     * @param sourceType     来源类型（AUTHORITY_DEFAULTS 键；未知 → 0.5）
     * @param freshness      显式新鲜度（可空；缺省由 publishedAt 推算，再缺省 0.5）
     * @param agreement      多源一致度（可空 → 0.0）
     * @param citationCount  引用/反向链接数（可空 → 0）
     * @param evidenceDensity 证据密度（可空 → 0.0）
     * @param publishedAt    原文发布时间（可空）
     * @param now            当前时间（测试可注入）
     */
    public Map<String, Object> computeCredibility(String sourceType,
                                                  Double freshness,
                                                  Double agreement,
                                                  Integer citationCount,
                                                  Double evidenceDensity,
                                                  OffsetDateTime publishedAt,
                                                  OffsetDateTime now) {
        double authority = AUTHORITY_DEFAULTS.getOrDefault(sourceType, 0.5);
        double fresh = freshness != null ? freshness : freshnessFromDate(publishedAt, now);
        double agree = agreement != null ? agreement : 0.0;
        double evidence = evidenceDensity != null ? evidenceDensity : 0.0;
        int citations = citationCount != null ? citationCount : 0;
        double citationNorm = citations > 0
            ? Math.min(citations / CITATION_NORM_DENOMINATOR, 1.0)
            : 0.0;

        double score = WEIGHTS.get("authority") * authority
            + WEIGHTS.get("freshness") * fresh
            + WEIGHTS.get("agreement") * agree
            + WEIGHTS.get("citation") * citationNorm
            + WEIGHTS.get("evidence") * evidence;

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("authority_score", round4(authority));
        result.put("freshness_score", round4(fresh));
        result.put("agreement_score", round4(agree));
        result.put("citation_count", citations);
        result.put("evidence_density", round4(evidence));
        result.put("credibility_score", round4(score));
        return result;
    }

    /**
     * RRF 融合阶段的权重调节器（对应 Python weight_by_credibility）：
     * 综合分 cred ∈ [0,1] → 乘数 (0.5 + cred) ∈ [0.5, 1.5]。
     * 文档缺省 credibility_score=0.5 → 乘数 1.0（恒等）。
     */
    public double weightByCredibility(double rrfContribution, Map<String, Object> doc) {
        Object credObj = doc.get("credibility_score");
        double cred = 0.5;
        if (credObj instanceof Number num) {
            cred = num.doubleValue();
        } else if (credObj != null) {
            try {
                cred = Double.parseDouble(String.valueOf(credObj));
            } catch (NumberFormatException e) {
                cred = 0.5;
            }
        }
        return rrfContribution * (0.5 + cred);
    }

    private double round4(double value) {
        return Math.round(value * 10000.0) / 10000.0;
    }
}
