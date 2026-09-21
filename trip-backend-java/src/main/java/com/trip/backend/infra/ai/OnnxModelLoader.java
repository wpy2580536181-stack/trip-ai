package com.trip.backend.infra.ai;

import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtSession;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * ONNX 模型加载器。
 *
 * - 从模型目录加载 model.onnx（bge-small-zh-v1.5 / bge-reranker-base）
 * - 模型文件缺失/损坏 → 抛异常，由调用方 fail-closed 降级
 */
@Component
public class OnnxModelLoader {

    private final OrtEnvironment environment;

    public OnnxModelLoader() {
        this.environment = OrtEnvironment.getEnvironment();
    }

    /**
     * 加载模型目录下的 model.onnx。
     *
     * @param modelPath 模型目录（如 models/bge-small-zh-v1.5）
     * @return OrtSession 会话
     * @throws Exception 模型文件不存在或加载失败
     */
    public OrtSession load(String modelPath) throws Exception {
        Path modelFile = Path.of(modelPath, "model.onnx");
        if (!Files.exists(modelFile)) {
            throw new IllegalStateException("onnx model not found: " + modelFile.toAbsolutePath());
        }
        return environment.createSession(modelFile.toString(), new OrtSession.SessionOptions());
    }

    public OrtEnvironment environment() {
        return environment;
    }
}
