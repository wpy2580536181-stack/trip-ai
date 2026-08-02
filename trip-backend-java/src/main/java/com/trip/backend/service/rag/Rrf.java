package com.trip.backend.service.rag;

import java.util.*;
import java.util.stream.Collectors;

/**
 * RRF (Reciprocal Rank Fusion) 融合算法
 *
 * 对应 Python services/rag/rrf.py
 *
 * 公式：RRF(d) = Σ (1 / (k + rank_i(d)))
 * k = 60（TREC 标准）
 */
public class Rrf {

    private static final int DEFAULT_K = 60;

    /**
     * RRF 融合
     *
     * @param resultsList 多个召回路径的结果列表
     * @param k RRF 常数（默认 60）
     * @param idKey 文档 ID 字段名
     * @return 融合排序后的结果列表
     */
    public <T> List<T> merge(List<List<T>> resultsList, int k, String idKey) {
        if (resultsList == null || resultsList.isEmpty()) {
            return List.of();
        }

        // 过滤空路径
        List<List<T>> validPaths = resultsList.stream()
            .filter(path -> path != null && !path.isEmpty())
            .collect(Collectors.toList());

        if (validPaths.isEmpty()) {
            return List.of();
        }

        // 计算 RRF 分数
        Map<String, RrfScore<T>> scoreMap = new HashMap<>();

        for (List<T> path : validPaths) {
            for (int rank = 0; rank < path.size(); rank++) {
                T doc = path.get(rank);
                String docId = extractId(doc, idKey);
                if (docId == null) {
                    continue;
                }

                double contribution = 1.0 / (k + rank);

                scoreMap.computeIfAbsent(docId, key -> new RrfScore<>(doc, 0.0))
                    .addScore(contribution);
            }
        }

        // 按分数降序排序
        return scoreMap.values().stream()
            .sorted(Comparator.comparingDouble(RrfScore::score).reversed())
            .map(score -> score.doc)
            .collect(Collectors.toList());
    }

    /**
     * 带权重的 RRF 融合
     *
     * @param resultsList 多个召回路径的结果列表
     * @param weights 权重列表
     * @param k RRF 常数
     * @param idKey 文档 ID 字段名
     * @return 融合排序后的结果列表
     */
    public <T> List<T> mergeWithWeights(List<List<T>> resultsList, List<Double> weights, int k, String idKey) {
        if (resultsList == null || weights == null || resultsList.size() != weights.size()) {
            throw new IllegalArgumentException("results_list and weights must have same length");
        }

        List<List<T>> validPaths = new ArrayList<>();
        List<Double> validWeights = new ArrayList<>();

        for (int i = 0; i < resultsList.size(); i++) {
            List<T> path = resultsList.get(i);
            if (path != null && !path.isEmpty()) {
                validPaths.add(path);
                validWeights.add(weights.get(i));
            }
        }

        if (validPaths.isEmpty()) {
            return List.of();
        }

        // 计算加权 RRF 分数
        Map<String, RrfScore<T>> scoreMap = new HashMap<>();

        for (int pathIdx = 0; pathIdx < validPaths.size(); pathIdx++) {
            List<T> path = validPaths.get(pathIdx);
            double weight = validWeights.get(pathIdx);

            for (int rank = 0; rank < path.size(); rank++) {
                T doc = path.get(rank);
                String docId = extractId(doc, idKey);
                if (docId == null) {
                    continue;
                }

                double contribution = weight / (k + rank);

                scoreMap.computeIfAbsent(docId, key -> new RrfScore<>(doc, 0.0))
                    .addScore(contribution);
            }
        }

        // 按分数降序排序
        return scoreMap.values().stream()
            .sorted(Comparator.comparingDouble(RrfScore::score).reversed())
            .map(score -> score.doc)
            .collect(Collectors.toList());
    }

    /**
     * 提取文档 ID（通过反射）
     */
    @SuppressWarnings("unchecked")
    private <T> String extractId(T doc, String idKey) {
        try {
            if (doc instanceof Map) {
                return String.valueOf(((Map<?, ?>) doc).get(idKey));
            }
            // 尝试反射获取字段
            java.lang.reflect.Field field = doc.getClass().getDeclaredField(idKey);
            field.setAccessible(true);
            Object value = field.get(doc);
            return value != null ? String.valueOf(value) : null;
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * RRF 分数记录
     */
    private static class RrfScore<T> {
        T doc;
        double score;

        RrfScore(T doc, double score) {
            this.doc = doc;
            this.score = score;
        }

        void addScore(double contribution) {
            this.score += contribution;
        }
    }
}
