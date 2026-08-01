package com.trip.backend.service.rag;

import java.util.ArrayList;
import java.util.List;

/**
 * 降级 Embedder（fail-closed 时使用，返回空向量）
 */
public class PassthroughEmbedder implements Embedder {

    private volatile boolean available = false;

    @Override
    public float[] embed(String text) {
        if (!available) {
            throw new IllegalStateException("Embedder 不可用（fail-closed）");
        }
        // 占位实现（ONNX 加载后替换）
        return new float[512];
    }

    @Override
    public List<float[]> embed(List<String> texts) {
        if (!available) {
            throw new IllegalStateException("Embedder 不可用（fail-closed）");
        }
        List<float[]> result = new ArrayList<>();
        for (String text : texts) {
            result.add(new float[512]);
        }
        return result;
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
