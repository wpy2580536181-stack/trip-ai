package com.trip.backend.service.rag;

import java.util.ArrayList;
import java.util.List;

/**
 * 降级 Reranker（不可用时保持原顺序）
 */
public class PassthroughReranker implements Reranker {

    private volatile boolean available = false;

    @Override
    public List<Double> score(String query, List<String> documents) {
        if (!available) {
            // 不可用时保持原顺序（返回 0 分）
            List<Double> scores = new ArrayList<>();
            for (int i = 0; i < documents.size(); i++) {
                scores.add(0.0);
            }
            return scores;
        }

        // 占位实现（ONNX 加载后替换）
        List<Double> scores = new ArrayList<>();
        for (int i = 0; i < documents.size(); i++) {
            scores.add(0.5); // 统一打分
        }
        return scores;
    }

    @Override
    public boolean isAvailable() {
        return available;
    }

    @Override
    public void markUnavailable() {
        this.available = false;
    }

    @Override
    public void warmup() {
        // TODO: 加载 ONNX 模型
        // this.available = true;
    }
}
