package com.trip.backend.infra.ai;

import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OnnxValue;
import ai.onnxruntime.OrtSession;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * BGE Embedder（bge-small-zh-v1.5，ONNX Runtime，对应 Python src/services/rag/embeddings.py）。
 *
 * - 查询文本加前缀"为这个句子生成表示以用于检索相关文章："（文档不加）
 * - WordPiece tokenizer + ONNX 推理
 * - 输出 L2 normalize（512 维）
 * - fail-closed：启动 markUnavailable()，后台 warmup() 成功才恢复；
 *   预热失败保持降级、不阻塞启动；不可用时 embed 返回 empty（不抛异常）
 */
@Component
public class BgeEmbedder {

    private static final Logger log = LoggerFactory.getLogger(BgeEmbedder.class);

    public static final String QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章：";
    public static final int DEFAULT_MAX_LENGTH = 512;

    private final EmbedderHealth health;
    private final OnnxModelLoader loader;
    private final String modelPath;
    private final int maxLength;

    private volatile OrtSession session;
    private volatile WordPieceTokenizer tokenizer;

    @Autowired
    public BgeEmbedder(EmbedderHealth health,
                       OnnxModelLoader loader,
                       @Value("${rag.embedding.model-path:models/bge-small-zh-v1.5}") String modelPath) {
        this(health, loader, modelPath, DEFAULT_MAX_LENGTH);
    }

    public BgeEmbedder(EmbedderHealth health, OnnxModelLoader loader, String modelPath, int maxLength) {
        this.health = health;
        this.loader = loader;
        this.modelPath = modelPath;
        this.maxLength = maxLength;
    }

    /** fail-closed 初始化：默认不可用，后台预热（不阻塞启动）。 */
    @PostConstruct
    public void init() {
        health.markUnavailable("embedding model not warmed up");
        Thread.ofVirtual().name("bge-embedder-warmup").start(() -> warmup());
    }

    /** 强制加载模型；成功 → 可用，失败 → 保持降级。返回是否成功。 */
    public boolean warmup() {
        try {
            Path dir = Path.of(modelPath);
            WordPieceTokenizer tok = WordPieceTokenizer.fromVocabFile(dir.resolve("vocab.txt"), maxLength);
            OrtSession newSession = loader.load(modelPath);
            this.tokenizer = tok;
            this.session = newSession;
            health.markAvailable();
            log.info("bge_embedder_warmup_done model={}", modelPath);
            return true;
        } catch (Exception e) {
            this.session = null;
            this.tokenizer = null;
            health.markUnavailable("embedding warmup failed: " + e.getMessage());
            log.warn("bge_embedder_warmup_failed（保持降级） model={} error={}", modelPath, e.getMessage());
            return false;
        }
    }

    /**
     * 查询文本 → 向量（加 BGE 查询前缀）。
     *
     * @return 512 维 L2 归一化向量；模型不可用/推理失败时返回 empty（降级，不抛异常）
     */
    public Optional<float[]> embed(String text) {
        if (text == null) {
            return Optional.empty();
        }
        return encodeAndPool(QUERY_PREFIX + text);
    }

    /** 文档文本 → 向量（不加前缀）。 */
    public Optional<float[]> embedDocument(String text) {
        if (text == null) {
            return Optional.empty();
        }
        return encodeAndPool(text);
    }

    private Optional<float[]> encodeAndPool(String text) {
        if (!health.isAvailable() || session == null || tokenizer == null) {
            return Optional.empty();
        }
        Map<String, OnnxTensor> tensors = null;
        try {
            WordPieceTokenizer.Tokens tokens = tokenizer.encode(text);
            tensors = inputTensors(tokens);
            try (OrtSession.Result result = session.run(tensors)) {
                OnnxValue output = result.get(0);
                float[] pooled = poolOutput(output, tokens.attentionMask());
                normalizeL2(pooled);
                return Optional.of(pooled);
            }
        } catch (Exception e) {
            // 推理失败 → fail-closed：标记不可用并降级
            health.markUnavailable("embedding inference failed: " + e.getMessage());
            log.error("bge_embedder_inference_failed error={}", e.getMessage());
            return Optional.empty();
        } finally {
            if (tensors != null) {
                for (OnnxTensor tensor : tensors.values()) {
                    try {
                        tensor.close();
                    } catch (Exception ignored) {
                        // 忽略关闭异常
                    }
                }
            }
        }
    }

    private Map<String, OnnxTensor> inputTensors(WordPieceTokenizer.Tokens tokens) throws Exception {
        Map<String, OnnxTensor> tensors = new LinkedHashMap<>();
        // 按 session 实际输入名提供张量（兼容不同导出配置的输入顺序/命名）
        for (String name : session.getInputNames()) {
            switch (name) {
                case "input_ids", "input" ->
                    tensors.put(name, OnnxTensor.createTensor(loader.environment(), new long[][]{tokens.inputIds()}));
                case "attention_mask" ->
                    tensors.put(name, OnnxTensor.createTensor(loader.environment(), new long[][]{tokens.attentionMask()}));
                case "token_type_ids" ->
                    tensors.put(name, OnnxTensor.createTensor(loader.environment(), new long[][]{tokens.tokenTypeIds()}));
                default -> {
                    // 未知输入（如动态轴）：跳过，避免非法张量
                }
            }
        }
        if (tensors.isEmpty()) {
            throw new IllegalStateException("onnx session has no recognizable inputs: " + session.getInputNames());
        }
        return tensors;
    }

    /** 处理模型输出：3D last_hidden_state → CLS pooling（BGE-small-zh-v1.5 配置 pooling_mode_cls_token=true）；2D 直接使用。 */
    private float[] poolOutput(OnnxValue output, long[] attentionMask) throws Exception {
        ai.onnxruntime.OnnxTensor tensor = (ai.onnxruntime.OnnxTensor) output;
        long[] shape = tensor.getInfo().getShape();
        if (shape.length == 3) {
            // [batch=1, seq, hidden] → CLS pooling：取第 0 个 token（[CLS]）的隐藏向量
            float[][][] data = (float[][][]) tensor.getValue();
            int hidden = (int) shape[2];
            float[] pooled = new float[hidden];
            for (int h = 0; h < hidden; h++) {
                pooled[h] = data[0][0][h];
            }
            return pooled;
        } else if (shape.length == 2) {
            // [batch=1, hidden] 已 pooling
            float[][] data = (float[][]) tensor.getValue();
            return data[0].clone();
        }
        throw new IllegalStateException("unexpected onnx output shape: " + java.util.Arrays.toString(shape));
    }

    /** L2 归一化（原地修改）。 */
    public static void normalizeL2(float[] vector) {
        double sumSq = 0;
        for (float v : vector) {
            sumSq += (double) v * v;
        }
        double norm = Math.sqrt(sumSq);
        if (norm < 1e-12) {
            return;
        }
        for (int i = 0; i < vector.length; i++) {
            vector[i] = (float) (vector[i] / norm);
        }
    }

    /** 余弦相似度（[-1, 1]，用于对拍验证）。 */
    public static double cosineSimilarity(float[] a, float[] b) {
        if (a.length != b.length) {
            throw new IllegalArgumentException("vector length mismatch");
        }
        double dot = 0, normA = 0, normB = 0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            normA += (double) a[i] * a[i];
            normB += (double) b[i] * b[i];
        }
        double denom = Math.sqrt(normA) * Math.sqrt(normB);
        return denom < 1e-12 ? 0.0 : dot / denom;
    }

    public EmbedderHealth health() {
        return health;
    }
}
