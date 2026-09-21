package com.trip.backend.infra.ai;

import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OnnxValue;
import ai.onnxruntime.OrtSession;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * BGE Reranker（bge-reranker-base CrossEncoder，ONNX Runtime，对应 Python src/services/rag/reranker.py）。
 *
 * - 查询-文档对 → logits → sigmoid 归一化到 (0,1)
 * - tokenizer：优先 vocab.txt（WordPiece）；也支持 vocab.json（XLM-R 风格）
 * - fail-closed：与 Embedder 同模式，预热失败保持降级、不阻塞启动；
 *   不可用时 rerank 返回 empty，由调用方降级为 RRF 原始顺序
 */
@Component
public class BgeReranker {

    private static final Logger log = LoggerFactory.getLogger(BgeReranker.class);

    private final OnnxModelLoader loader;
    private final String modelPath;
    private final int maxLength;

    private volatile OrtSession session;
    private volatile WordPieceTokenizer tokenizer;
    private volatile boolean available = false;
    private volatile String reason = "not warmed up";

    public BgeReranker(OnnxModelLoader loader,
                       @Value("${rag.reranker.model-path:models/bge-reranker-base}") String modelPath) {
        this(loader, modelPath, 512);
    }

    public BgeReranker(OnnxModelLoader loader, String modelPath, int maxLength) {
        this.loader = loader;
        this.modelPath = modelPath;
        this.maxLength = maxLength;
    }

    @PostConstruct
    public void init() {
        available = false;
        Thread.ofVirtual().name("bge-reranker-warmup").start(() -> warmup());
    }

    /** 强制加载；成功 → 可用，失败 → 保持降级。返回是否成功。 */
    public boolean warmup() {
        try {
            Path dir = Path.of(modelPath);
            WordPieceTokenizer tok;
            if (Files.exists(dir.resolve("vocab.txt"))) {
                tok = WordPieceTokenizer.fromVocabFile(dir.resolve("vocab.txt"), maxLength);
            } else if (Files.exists(dir.resolve("vocab.json"))) {
                tok = WordPieceTokenizer.fromVocabJson(dir.resolve("vocab.json"), maxLength);
            } else {
                throw new IllegalStateException("reranker tokenizer not found (need vocab.txt or vocab.json) in " + dir);
            }
            OrtSession newSession = loader.load(modelPath);
            this.tokenizer = tok;
            this.session = newSession;
            this.available = true;
            this.reason = "ok";
            log.info("bge_reranker_warmup_done model={}", modelPath);
            return true;
        } catch (Exception e) {
            this.session = null;
            this.tokenizer = null;
            this.available = false;
            this.reason = "reranker warmup failed: " + e.getMessage();
            log.warn("bge_reranker_warmup_failed（保持降级） model={} error={}", modelPath, e.getMessage());
            return false;
        }
    }

    public boolean isAvailable() {
        return available;
    }

    public String getReason() {
        return reason;
    }

    /**
     * 对候选文档重排序（query × doc pairs → sigmoid 分数）。
     *
     * @return 与 documents 对齐的分数列表（0~1）；模型不可用/推理失败时 empty（降级由调用方处理）
     */
    public Optional<List<Double>> rerank(String query, List<String> documents) {
        if (!available || session == null || tokenizer == null || documents == null || documents.isEmpty()) {
            return Optional.empty();
        }
        List<Double> scores = new ArrayList<>(documents.size());
        for (String doc : documents) {
            try {
                scores.add(scorePair(query, doc));
            } catch (Exception e) {
                log.error("bge_reranker_inference_failed error={}", e.getMessage());
                this.available = false;
                this.reason = "reranker inference failed: " + e.getMessage();
                return Optional.empty();
            }
        }
        return Optional.of(scores);
    }

    private double scorePair(String query, String doc) throws Exception {
        // 构造 [CLS] query [SEP] doc [SEP]（CrossEncoder 标准输入）
        String pair = query + " [SEP] " + doc;
        WordPieceTokenizer.Tokens tokens = tokenizer.encode(pair, maxLength);

        Map<String, OnnxTensor> tensors = new LinkedHashMap<>();
        try {
            for (String name : session.getInputNames()) {
                switch (name) {
                    case "input_ids", "input" ->
                        tensors.put(name, OnnxTensor.createTensor(loader.environment(), new long[][]{tokens.inputIds()}));
                    case "attention_mask" ->
                        tensors.put(name, OnnxTensor.createTensor(loader.environment(), new long[][]{tokens.attentionMask()}));
                    case "token_type_ids" ->
                        tensors.put(name, OnnxTensor.createTensor(loader.environment(), new long[][]{tokens.tokenTypeIds()}));
                    default -> {
                        // 跳过未知输入
                    }
                }
            }
            if (tensors.isEmpty()) {
                throw new IllegalStateException("onnx session has no recognizable inputs");
            }
            try (OrtSession.Result result = session.run(tensors)) {
                OnnxValue output = result.get(0);
                OnnxTensor tensor = (OnnxTensor) output;
                float[][] logits = (float[][]) tensor.getValue();
                return sigmoid(logits[0][0]);
            }
        } finally {
            for (OnnxTensor tensor : tensors.values()) {
                try {
                    tensor.close();
                } catch (Exception ignored) {
                    // ignore
                }
            }
        }
    }

    /** sigmoid 归一化（对应 Python torch.sigmoid / 纯 Python 兜底）。 */
    public static double sigmoid(double x) {
        if (x >= 0) {
            double z = Math.exp(-x);
            return 1.0 / (1.0 + z);
        }
        double z = Math.exp(x);
        return z / (1.0 + z);
    }
}
