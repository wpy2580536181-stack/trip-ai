package com.trip.backend.service.rag;

import java.util.List;

/**
 * Reranker 接口（对应 Python rag/reranker.py）
 */
public interface Reranker {

    /**
     * 对 (query, document) 对进行重排序打分
     *
     * @param query 查询文本
     * @param documents 文档列表
     * @return 打分列表（与 documents 同序）
     */
    List<Double> score(String query, List<String> documents);

    /**
     * 检查是否可用
     */
    boolean isAvailable();

    /**
     * 标记为不可用
     */
    void markUnavailable();

    /**
     * 预热
     */
    void warmup();
}
