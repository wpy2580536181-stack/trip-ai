package com.trip.backend.service.rag;

import org.springframework.stereotype.Service;

import java.util.List;

/**
 * 可信度重排
 *
 * 对应 Python services/rag/reranker.py + credibility 重排逻辑
 *
 * 公式：
 * - rerank sigmoid 转换
 * - final = (1-w) * rerank + w * cred
 * - w = 0.3
 *
 * 降级：模型不可用 → 返回原始顺序
 */
@Service
public class RerankWithCredibility {

    private static final double WEIGHT_CREDIBILITY = 0.3;
    private static final double WEIGHT_RERANK = 1.0 - WEIGHT_CREDIBILITY;

    private final CredibilityService credibilityService;

    public RerankWithCredibility(CredibilityService credibilityService) {
        this.credibilityService = credibilityService;
    }

    /**
     * 重排（带可信度）
     *
     * @param results 检索结果列表
     * @param query 查询文本（用于 rerank 模型）
     * @param limit 返回数量
     * @return 重排后的结果列表
     */
    public <T extends Rankable> List<T> rerank(List<T> results, String query, int limit) {
        if (results == null || results.isEmpty()) {
            return List.of();
        }

        try {
            // 1. 计算 rerank 分数（简化版：用 score 模拟）
            // TODO: C3 集成真实 rerank 模型
            for (T result : results) {
                double rerankScore = result.getScore(); // 简化：直接用原始分数

                // 2. 计算可信度
                double credibility = calculateCredibilityForItem(result);

                // 3. 加权融合
                double finalScore = WEIGHT_RERANK * rerankScore + WEIGHT_CREDIBILITY * credibility;
                result.setScore(finalScore);
            }

            // 4. 按分数降序排序
            return results.stream()
                .sorted((a, b) -> Double.compare(b.getScore(), a.getScore()))
                .limit(limit)
                .toList();

        } catch (Exception e) {
            // 降级：返回原始顺序
            return results.subList(0, Math.min(results.size(), limit));
        }
    }

    /**
     * 计算条目的可信度
     */
    private double calculateCredibilityForItem(Rankable item) {
        // 简化版：使用 spot_docs 的 credibility_score，否则用默认值
        if (item instanceof SpotDoc spotDoc) {
            return spotDoc.getCredibilityScore() != null
                ? spotDoc.getCredibilityScore()
                : 0.5;
        }

        // spots 默认可信度
        return 0.5;
    }

    /**
     * 可排序条目接口
     */
    public interface Rankable {
        double getScore();
        void setScore(double score);
    }
}
