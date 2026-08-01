package com.trip.backend.service.rag;

import java.util.List;

/**
 * Embedder 接口（对应 Python rag/embeddings.py）
 */
public interface Embedder {

    /**
     * 嵌入单个文本
     */
    float[] embed(String text);

    /**
     * 批量嵌入
     */
    List<float[]> embed(List<String> texts);

    /**
     * 检查是否可用（fail-closed 状态）
     */
    boolean isAvailable();

    /**
     * 标记为不可用
     */
    void markUnavailable();

    /**
     * 预热（后台加载模型）
     */
    void warmup();
}
