package com.trip.backend.test.unit;

import com.trip.backend.infra.ai.BgeEmbedder;
import com.trip.backend.infra.ai.BgeReranker;
import com.trip.backend.infra.ai.EmbedderHealth;
import com.trip.backend.infra.ai.OnnxModelLoader;
import com.trip.backend.infra.ai.WordPieceTokenizer;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-C1 ONNX Embedder/Reranker 单元测试。
 *
 * - tokenizer 用真实 vocab.txt（models/bge-small-zh-v1.5/vocab.txt，21128 词）
 * - embedder/reranker fail-closed 行为：未预热 / 预热失败（无 model.onnx）→ 降级不抛异常
 * - [需真实环境] 项（余弦对拍 ≥0.999）依赖 ONNX 模型 + PostgreSQL，本机不可执行
 */
class OnnxAiTest {

    private static final Path VOCAB = Path.of("models/bge-small-zh-v1.5/vocab.txt");

    // ------------------------------------------------------------------
    // WordPieceTokenizer（真实 vocab）
    // ------------------------------------------------------------------

    @Test
    void tokenizerEncodesChineseWithClsSep() throws Exception {
        WordPieceTokenizer tokenizer = WordPieceTokenizer.fromVocabFile(VOCAB, 512);
        WordPieceTokenizer.Tokens tokens = tokenizer.encode("北京故宫");

        assertEquals(512, tokens.inputIds().length);
        assertEquals(WordPieceTokenizer.CLS_ID, tokens.inputIds()[0], "首位应为 [CLS]");
        assertEquals(1, tokens.attentionMask()[0]);

        // 北京故宫 → 4 个汉字 token + [CLS] + [SEP] = 6 个有效位
        assertEquals(6, countActive(tokens.attentionMask()));
        assertEquals(WordPieceTokenizer.SEP_ID, tokens.inputIds()[countActive(tokens.attentionMask()) - 1], "末位应为 [SEP]");

        // 有效区域之后应为 PAD(0)
        assertEquals(0, tokens.inputIds()[countActive(tokens.attentionMask())]);
        assertEquals(0, tokens.attentionMask()[countActive(tokens.attentionMask())]);
    }

    @Test
    void tokenizerTruncatesLongText() throws Exception {
        WordPieceTokenizer tokenizer = WordPieceTokenizer.fromVocabFile(VOCAB, 512);
        String longText = "北京".repeat(1000);
        WordPieceTokenizer.Tokens tokens = tokenizer.encode(longText);

        // [CLS] + 510 tokens + [SEP] = 512
        assertEquals(512, countActive(tokens.attentionMask()), "长文本应截断到 maxLength-2 个 token");
    }

    @Test
    void tokenizerHandlesUnknownTokenAsUnk() throws Exception {
        WordPieceTokenizer tokenizer = WordPieceTokenizer.fromVocabFile(VOCAB, 512);
        // 生僻字（CJK 扩展 B，vocab 中不存在）→ [UNK]
        WordPieceTokenizer.Tokens tokens = tokenizer.encode("\uD840\uDDF7"); // U+20BB7 𠮷
        int active = countActive(tokens.attentionMask());
        boolean hasUnk = false;
        for (int i = 0; i < active; i++) {
            if (tokens.inputIds()[i] == WordPieceTokenizer.UNK_ID) {
                hasUnk = true;
                break;
            }
        }
        assertTrue(hasUnk, "未知字符应映射为 [UNK]");
    }

    @Test
    void vocabJsonLoadingWorks() throws Exception {
        // 用临时 vocab.json 验证 XLM-R 风格加载
        java.nio.file.Path tmp = java.nio.file.Files.createTempFile("vocab", ".json");
        java.nio.file.Files.writeString(tmp, "{\"[PAD]\":0,\"[UNK]\":1,\"[CLS]\":2,\"[SEP]\":3,\"北\":4,\"京\":5}");
        WordPieceTokenizer tokenizer = WordPieceTokenizer.fromVocabJson(tmp, 8);
        assertEquals(6, tokenizer.vocabSize());
        java.nio.file.Files.deleteIfExists(tmp);
    }

    private int countActive(long[] mask) {
        int count = 0;
        for (long m : mask) {
            if (m == 1) {
                count++;
            }
        }
        return count;
    }

    // ------------------------------------------------------------------
    // BgeEmbedder（fail-closed）
    // ------------------------------------------------------------------

    @Test
    void embedderDegradesBeforeWarmup() {
        EmbedderHealth health = new EmbedderHealth();
        OnnxModelLoader loader = new OnnxModelLoader();
        BgeEmbedder embedder = new BgeEmbedder(health, loader, "models/bge-small-zh-v1.5", 512);

        assertFalse(health.isAvailable(), "启动时应 fail-closed（未预热不可用）");
        Optional<float[]> vec = embedder.embed("北京故宫");
        assertFalse(vec.isPresent(), "未预热时 embed 应降级（返回 empty，不抛异常）");
        assertEquals(EmbedderHealth.State.UNAVAILABLE, health.getState());
    }

    @Test
    void embedderWarmupFailureKeepsDegradedAndAppStillStarts() {
        EmbedderHealth health = new EmbedderHealth();
        OnnxModelLoader loader = new OnnxModelLoader();
        // 用不存在目录测降级（不依赖真实 model.onnx 是否就位）
        BgeEmbedder embedder = new BgeEmbedder(health, loader, "target/test-models/does-not-exist-xyz", 512);

        // 目录不存在 → warmup 失败
        boolean warmed = embedder.warmup();
        assertFalse(warmed, "无 model.onnx 时预热应失败");
        assertFalse(health.isAvailable(), "预热失败应保持不可用");
        assertFalse(embedder.embed("北京").isPresent(), "预热失败后 embed 仍应降级（不抛异常）");
        assertNotNull(health.getReason());
    }

    @Test
    void normalizeL2AndCosine() {
        float[] v = {3.0f, 4.0f};
        BgeEmbedder.normalizeL2(v);
        assertEquals(1.0, Math.sqrt(v[0] * v[0] + v[1] * v[1]), 1e-6, "L2 归一化后范数应为 1");

        float[] a = {1, 0, 0};
        float[] b = {0, 1, 0};
        assertEquals(0.0, BgeEmbedder.cosineSimilarity(a, b), 1e-9);
        assertEquals(1.0, BgeEmbedder.cosineSimilarity(a, a), 1e-9);
        assertEquals(-1.0, BgeEmbedder.cosineSimilarity(a, new float[]{-1, 0, 0}), 1e-9);
    }

    // ------------------------------------------------------------------
    // BgeReranker（fail-closed + sigmoid）
    // ------------------------------------------------------------------

    @Test
    void rerankerDegradesBeforeWarmup() {
        OnnxModelLoader loader = new OnnxModelLoader();
        BgeReranker reranker = new BgeReranker(loader, "models/bge-reranker-base", 512);

        assertFalse(reranker.isAvailable(), "未预热不可用");
        Optional<List<Double>> scores = reranker.rerank("北京", List.of("故宫", "长城"));
        assertFalse(scores.isPresent(), "未预热时 rerank 应返回 empty（降级由调用方处理）");
    }

    @Test
    void rerankerWarmupFailureKeepsDegraded() {
        OnnxModelLoader loader = new OnnxModelLoader();
        BgeReranker reranker = new BgeReranker(loader, "models/bge-reranker-base", 512);

        // 目录无 tokenizer 文件也无 model.onnx → warmup 失败
        boolean warmed = reranker.warmup();
        assertFalse(warmed, "无模型文件时预热应失败");
        assertFalse(reranker.isAvailable());
        assertFalse(reranker.rerank("q", List.of("d")).isPresent());
    }

    @Test
    void sigmoidNormalization() {
        assertEquals(0.5, BgeReranker.sigmoid(0), 1e-9);
        assertEquals(1.0, BgeReranker.sigmoid(100), 1e-6, "大正数 → ~1");
        assertEquals(0.0, BgeReranker.sigmoid(-100), 1e-9, "大负数 → ~0");
        assertEquals(0.7310585786, BgeReranker.sigmoid(1), 1e-6);
    }
}
