package com.trip.backend.test.unit;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.BgeReranker;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import com.trip.backend.service.rag.CredibilityService;
import com.trip.backend.service.rag.RerankWithCredibility;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C3 CredibilityService + RerankWithCredibility 单元测试（纯内存）。
 */
class CredibilityRerankTest {

    private final CredibilityService credibility = new CredibilityService();

    // ------------------------------------------------------------------
    // CredibilityService
    // ------------------------------------------------------------------

    @Test
    void freshnessFromDateLinearDecay() {
        OffsetDateTime now = OffsetDateTime.of(2026, 9, 21, 12, 0, 0, 0, ZoneOffset.UTC);
        // ≤30 天 → 1.0
        assertEquals(1.0, credibility.freshnessFromDate(now.minusDays(30), now), 1e-9);
        assertEquals(1.0, credibility.freshnessFromDate(now.minusDays(1), now), 1e-9);
        // ≥365 天 → 0.0
        assertEquals(0.0, credibility.freshnessFromDate(now.minusDays(365), now), 1e-9);
        assertEquals(0.0, credibility.freshnessFromDate(now.minusDays(1000), now), 1e-9);
        // 中间线性衰减：第 30~365 天之间
        // days=197.5 → 1 - (197.5-30)/335 = 0.5（取整 days=197 → 0.5015）
        double mid = credibility.freshnessFromDate(now.minusDays(197), now);
        assertTrue(mid > 0.49 && mid < 0.52, "mid decay: " + mid);
        // null → 0.5
        assertEquals(0.5, credibility.freshnessFromDate(null, now), 1e-9);
    }

    @Test
    void computeCredibilityWikiDefaults() {
        // wiki: authority=1.0, freshness 缺省(无发布时间→0.5), agreement 0, citation 0, evidence 0
        Map<String, Object> r = credibility.computeCredibility("wiki", null, null, null, null, null, null);
        assertEquals(1.0, (Double) r.get("authority_score"), 1e-9);
        assertEquals(0.5, (Double) r.get("freshness_score"), 1e-9);
        // 0.35*1.0 + 0.20*0.5 = 0.45
        assertEquals(0.45, (Double) r.get("credibility_score"), 1e-9);
    }

    @Test
    void computeCredibilityUnknownSourceDefaultsToHalf() {
        Map<String, Object> r = credibility.computeCredibility("unknown_type", 0.5, 0.0, 0, 0.0, null, null);
        assertEquals(0.5, (Double) r.get("authority_score"), 1e-9);
    }

    @Test
    void computeCredibilityCitationNormalization() {
        // citation_count=50 → 归一化 1.0；100 → cap 1.0
        Map<String, Object> r50 = credibility.computeCredibility("wiki", 1.0, 1.0, 50, 1.0, null, null);
        assertEquals(0.35 + 0.20 + 0.20 + 0.15 + 0.10, (Double) r50.get("credibility_score"), 1e-9);
        Map<String, Object> r100 = credibility.computeCredibility("wiki", 1.0, 1.0, 100, 1.0, null, null);
        assertEquals(r50.get("credibility_score"), r100.get("credibility_score"));
    }

    @Test
    void weightByCredibilityScalesContribution() {
        Map<String, Object> doc = new LinkedHashMap<>();
        // 缺省 cred=0.5 → 乘数 1.0（恒等）
        assertEquals(0.1, credibility.weightByCredibility(0.1, doc), 1e-9);

        doc.put("credibility_score", 1.0);
        assertEquals(0.15, credibility.weightByCredibility(0.1, doc), 1e-9);

        doc.put("credibility_score", "0.8");
        assertEquals(0.13, credibility.weightByCredibility(0.1, doc), 1e-9);
    }

    // ------------------------------------------------------------------
    // RerankWithCredibility（reranker 不可用 → 降级）
    // ------------------------------------------------------------------

    @Test
    void rerankDegradesToCredibilityOrderWhenModelUnavailable() {
        // BgeReranker 未预热 → 不可用 → rerank 返回 empty → 降级 score=0，final=0.3*cred
        BgeReranker reranker = new BgeReranker(new OnnxModelLoader(), "models/bge-reranker-base", 512);
        RerankWithCredibility rerank = new RerankWithCredibility(reranker, 0.3);

        Map<String, Object> wikiDoc = doc("1", "故宫", 1.0);
        Map<String, Object> ugcDoc = doc("2", "长城", 0.4);
        List<Map<String, Object>> out = rerank.rerank("故宫", List.of(ugcDoc, wikiDoc));

        // 按 credibility 降序：wiki(1.0) 在前
        assertEquals("1", out.get(0).get("id"));
        assertEquals("2", out.get(1).get("id"));
        assertEquals(0, (Double) out.get(0).get("score"), 1e-9, "模型不可用 → score=0.0");
        assertEquals(0.3 * 1.0, (Double) out.get(0).get("final_score"), 1e-9);
        assertEquals(0, out.get(0).get("rank"));
        assertEquals(1, out.get(1).get("rank"));
    }

    @Test
    void rerankDefaultCredibilityIsHalf() {
        BgeReranker reranker = new BgeReranker(new OnnxModelLoader(), "models/bge-reranker-base", 512);
        RerankWithCredibility rerank = new RerankWithCredibility(reranker, 0.3);

        Map<String, Object> a = doc("1", "故宫", null); // 无 credibility → 0.5
        Map<String, Object> b = doc("2", "长城", 0.9);
        List<Map<String, Object>> out = rerank.rerank("故宫", List.of(a, b));

        assertEquals("2", out.get(0).get("id"), "cred 0.9 > 0.5");
        assertEquals(0.3 * 0.5, (Double) out.get(1).get("final_score"), 1e-9);
    }

    @Test
    void rerankDocTextPrefersEvidenceContent() {
        BgeReranker reranker = new BgeReranker(new OnnxModelLoader(), "models/bge-reranker-base", 512);
        RerankWithCredibility rerank = new RerankWithCredibility(reranker, 0.3);

        Map<String, Object> doc = new LinkedHashMap<>();
        doc.put("id", "9");
        doc.put("name", "故宫");
        doc.put("description", "建筑群");
        Map<String, Object> evidence = new LinkedHashMap<>();
        evidence.put("content", "文本层真实内容：紫禁城历史");
        doc.put("evidence", evidence);

        List<Map<String, Object>> out = rerank.rerank("故宫", List.of(doc));
        assertEquals(1, out.size());
        assertEquals("9", out.get(0).get("id"));
        Map<?, ?> ev = (Map<?, ?>) out.get(0).get("evidence");
        assertEquals("文本层真实内容：紫禁城历史", ev.get("content"), "evidence 保留在 doc 中供上层使用");
    }

    @Test
    void rerankEmptyInputReturnsEmpty() {
        BgeReranker reranker = new BgeReranker(new OnnxModelLoader(), "models/bge-reranker-base", 512);
        RerankWithCredibility rerank = new RerankWithCredibility(reranker, 0.3);
        assertTrue(rerank.rerank("q", List.of()).isEmpty());
    }

    private Map<String, Object> doc(String id, String name, Double cred) {
        Map<String, Object> d = new LinkedHashMap<>();
        d.put("id", id);
        d.put("name", name);
        d.put("description", "描述 " + name);
        if (cred != null) {
            d.put("credibility_score", cred);
        }
        return d;
    }
}
