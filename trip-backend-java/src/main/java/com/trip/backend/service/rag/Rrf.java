package com.trip.backend.service.rag;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;

/**
 * RRF（Reciprocal Rank Fusion）融合算法（对应 Python src/services/rag/rrf.py）。
 *
 * 公式: RRF(d) = Σ (weight_i / (k + rank_i(d)))，rank 从 0 开始。
 * k 默认 60（与 TREC 标准一致）。
 */
public final class Rrf {

    public static final int DEFAULT_K = 60;

    private Rrf() {
    }

    /**
     * 普通 RRF 融合（权重均为 1）。
     *
     * @param resultsList 多个召回路径的结果列表
     * @param k           RRF 常数
     * @param idKey       文档唯一标识字段名
     * @return 融合排序结果（每项含 _rrf_score）
     */
    public static List<Map<String, Object>> rrfMerge(
        List<List<Map<String, Object>>> resultsList, int k, String idKey) {
        return merge(resultsList, null, k, idKey, null);
    }

    /**
     * 带权重的 RRF 融合。
     *
     * @param resultsList 多个召回路径的结果列表
     * @param weights     每个路径的权重（长度必须与 resultsList 一致；空路径不消耗权重）
     * @param k           RRF 常数
     * @param idKey       文档唯一标识字段名
     * @throws IllegalArgumentException resultsList 与 weights 长度不一致
     */
    public static List<Map<String, Object>> rrfMergeWithWeights(
        List<List<Map<String, Object>>> resultsList, List<Double> weights, int k, String idKey) {
        return rrfMergeWithWeights(resultsList, weights, k, idKey, null);
    }

    /**
     * 带权重 + 贡献调节器的 RRF 融合（对应 Python score_adjuster，如 weight_by_credibility）。
     *
     * @param resultsList 多个召回路径的结果列表
     * @param weights     每个路径的权重（长度必须与 resultsList 一致）
     * @param k           RRF 常数
     * @param idKey       文档唯一标识字段名
     * @param adjuster    单路贡献调节器（入参：原始贡献 weight/(k+rank)、文档；出参：调节后贡献；null 表示不调节）
     */
    public static List<Map<String, Object>> rrfMergeWithWeights(
        List<List<Map<String, Object>>> resultsList, List<Double> weights, int k, String idKey,
        BiFunction<Double, Map<String, Object>, Double> adjuster) {
        if (weights != null && resultsList.size() != weights.size()) {
            throw new IllegalArgumentException(
                "resultsList 和 weights 长度不一致: " + resultsList.size() + " vs " + weights.size());
        }
        return merge(resultsList, weights, k, idKey, adjuster);
    }

    private static List<Map<String, Object>> merge(
        List<List<Map<String, Object>>> resultsList, List<Double> weights, int k, String idKey,
        BiFunction<Double, Map<String, Object>, Double> adjuster) {
        if (resultsList == null || resultsList.isEmpty()) {
            return List.of();
        }
        // 过滤空路径（同时过滤对应权重）
        List<List<Map<String, Object>>> validPaths = new ArrayList<>();
        List<Double> validWeights = new ArrayList<>();
        for (int i = 0; i < resultsList.size(); i++) {
            List<Map<String, Object>> path = resultsList.get(i);
            if (path != null && !path.isEmpty()) {
                validPaths.add(path);
                validWeights.add(weights == null ? 1.0 : weights.get(i));
            }
        }
        if (validPaths.isEmpty()) {
            return List.of();
        }

        // 计算每个文档的 RRF 分数
        Map<String, Map<String, Object>> scoreMap = new LinkedHashMap<>(); // id -> {doc, score}
        for (int pathIdx = 0; pathIdx < validPaths.size(); pathIdx++) {
            double weight = validWeights.get(pathIdx);
            List<Map<String, Object>> path = validPaths.get(pathIdx);
            for (int rank = 0; rank < path.size(); rank++) {
                Map<String, Object> doc = path.get(rank);
                Object idObj = doc.get(idKey);
                if (idObj == null) {
                    continue;
                }
                String docId = String.valueOf(idObj);
                double contribution = weight / (k + rank);
                if (adjuster != null) {
                    try {
                        contribution = adjuster.apply(contribution, doc);
                    } catch (Exception e) {
                        // score_adjuster 失败 → 使用原始贡献
                    }
                }
                Map<String, Object> entry = scoreMap.get(docId);
                if (entry == null) {
                    Map<String, Object> docCopy = new LinkedHashMap<>(doc);
                    entry = new LinkedHashMap<>();
                    entry.put("doc", docCopy);
                    entry.put("score", contribution);
                    scoreMap.put(docId, entry);
                } else {
                    entry.put("score", (Double) entry.get("score") + contribution);
                }
            }
        }

        // 按 RRF 分数降序排序
        List<Map<String, Object>> sorted = new ArrayList<>(scoreMap.values());
        sorted.sort((a, b) -> Double.compare((Double) b.get("score"), (Double) a.get("score")));

        // 组装最终结果
        List<Map<String, Object>> merged = new ArrayList<>(sorted.size());
        for (Map<String, Object> item : sorted) {
            @SuppressWarnings("unchecked")
            Map<String, Object> doc = (Map<String, Object>) item.get("doc");
            doc.put("_rrf_score", item.get("score"));
            merged.add(doc);
        }
        return merged;
    }
}
