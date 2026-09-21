package com.trip.backend.service.rag;

import com.trip.backend.infra.ai.BgeReranker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 带可信度后置微调的重排序（对应 Python src/services/rag/reranker.py rerank_with_credibility）。
 *
 * final_score = (1 - w) * rerank_score + w * credibility_score，w 默认 0.3。
 * - rerank 模型不可用 / 预测失败 → 降级原始顺序（score=0.0），最终按 credibility 排序
 * - 文档缺省 credibility_score=0.5
 */
@Component
public class RerankWithCredibility {

    private static final Logger log = LoggerFactory.getLogger(RerankWithCredibility.class);

    private final BgeReranker reranker;
    private final double credibilityWeight;

    public RerankWithCredibility(BgeReranker reranker,
                                 @Value("${rag.retrieval.credibility.weight:0.3}") double credibilityWeight) {
        this.reranker = reranker;
        this.credibilityWeight = credibilityWeight;
    }

    /**
     * 对候选文档重排序（叠加可信度特征）。
     *
     * @param query     查询文本
     * @param documents 候选文档（RRF 融合结果，spot 级，可含 evidence/credibility_score）
     * @return 重排后的文档列表（原地补 score/final_score/rank 字段并排序）；空输入返回空
     */
    public List<Map<String, Object>> rerank(String query, List<Map<String, Object>> documents) {
        if (documents == null || documents.isEmpty()) {
            return List.of();
        }
        List<String> texts = documents.stream().map(this::docText).toList();

        // Cross-Encoder 相关性分数；不可用 → 降级 score=0（原始顺序）
        List<Double> scores;
        try {
            Optional<List<Double>> opt = reranker.rerank(query, texts);
            scores = opt.orElseGet(() -> zeroScores(texts.size()));
        } catch (Exception e) {
            log.warn("rerank_with_credibility_failed，降级原始顺序 error={}", e.getMessage());
            scores = zeroScores(texts.size());
        }

        // final = (1-w)*score + w*cred
        List<Scored> scored = new ArrayList<>(documents.size());
        for (int i = 0; i < documents.size(); i++) {
            Map<String, Object> doc = documents.get(i);
            double cred = credibilityOf(doc);
            double rerankScore = i < scores.size() ? scores.get(i) : 0.0;
            double finalScore = (1.0 - credibilityWeight) * rerankScore + credibilityWeight * cred;
            scored.add(new Scored(doc, rerankScore, finalScore));
        }

        // 稳定排序（final_score 降序）
        scored.sort((a, b) -> Double.compare(b.finalScore, a.finalScore));

        List<Map<String, Object>> out = new ArrayList<>(scored.size());
        for (int i = 0; i < scored.size(); i++) {
            Scored s = scored.get(i);
            s.doc.put("score", s.rerankScore);
            s.doc.put("final_score", s.finalScore);
            s.doc.put("rank", i);
            out.add(s.doc);
        }
        return out;
    }

    private List<Double> zeroScores(int size) {
        List<Double> zeros = new ArrayList<>(size);
        for (int i = 0; i < size; i++) {
            zeros.add(0.0);
        }
        return zeros;
    }

    /** 文档文本：优先 evidence.content（文本层真实内容），否则 name + description。 */
    private String docText(Map<String, Object> doc) {
        Object evidence = doc.get("evidence");
        if (evidence instanceof Map<?, ?> ev) {
            Object content = ev.get("content");
            if (content != null && !String.valueOf(content).isBlank()) {
                return String.valueOf(content);
            }
        }
        String name = doc.get("name") == null ? "" : String.valueOf(doc.get("name"));
        String desc = doc.get("description") == null ? "" : String.valueOf(doc.get("description"));
        return (name + " " + desc).trim();
    }

    private double credibilityOf(Map<String, Object> doc) {
        Object credObj = doc.get("credibility_score");
        if (credObj instanceof Number num) {
            return num.doubleValue();
        }
        if (credObj != null) {
            try {
                return Double.parseDouble(String.valueOf(credObj));
            } catch (NumberFormatException e) {
                // 缺省
            }
        }
        return 0.5;
    }

    private record Scored(Map<String, Object> doc, double rerankScore, double finalScore) {
    }
}
