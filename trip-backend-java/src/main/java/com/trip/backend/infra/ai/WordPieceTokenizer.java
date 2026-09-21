package com.trip.backend.infra.ai;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * WordPiece Tokenizer（bge-small-zh-v1.5，对应 Python BertTokenizer）。
 *
 * - 词汇来源：vocab.txt（每行一个 token）或 vocab.json（{token: id}，XLM-R 风格）
 * - special tokens：[PAD]=0, [UNK]=100, [CLS]=101, [SEP]=102, [MASK]=103
 * - 中文按字符切分（CJK 字符单独成 token），英文/数字做 WordPiece 子词
 * - 输出 [CLS] + tokens + [SEP]，truncate + pad 到 maxLength
 */
public class WordPieceTokenizer {

    public static final int PAD_ID = 0;
    public static final int UNK_ID = 100;
    public static final int CLS_ID = 101;
    public static final int SEP_ID = 102;
    public static final int MASK_ID = 103;

    private final Map<String, Integer> vocab;
    private final int maxLength;

    public WordPieceTokenizer(Map<String, Integer> vocab, int maxLength) {
        this.vocab = new HashMap<>(vocab);
        this.maxLength = maxLength;
    }

    /** 从 vocab.txt（每行一个 token，行号即 id）加载。 */
    public static WordPieceTokenizer fromVocabFile(Path vocabFile, int maxLength) throws IOException {
        List<String> lines = Files.readAllLines(vocabFile, StandardCharsets.UTF_8);
        Map<String, Integer> vocab = new HashMap<>(lines.size());
        for (int i = 0; i < lines.size(); i++) {
            String token = lines.get(i).trim();
            if (!token.isEmpty()) {
                vocab.put(token, i);
            }
        }
        return new WordPieceTokenizer(vocab, maxLength);
    }

    /** 从 vocab.json（{token: id} 映射）加载。 */
    public static WordPieceTokenizer fromVocabJson(Path vocabJson, int maxLength) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        Map<String, Integer> vocab = mapper.readValue(vocabJson.toFile(), new TypeReference<>() {
        });
        return new WordPieceTokenizer(vocab, maxLength);
    }

    /** 编码结果：input_ids / attention_mask / token_type_ids（长度均为 maxLength）。 */
    public record Tokens(long[] inputIds, long[] attentionMask, long[] tokenTypeIds) {
    }

    /**
     * 编码单条文本。
     *
     * @param text      输入文本（调用方负责加 BGE 查询前缀或保持原样）
     * @param maxLength 序列长度上限（超出截断、不足填充）
     */
    public Tokens encode(String text, int maxLength) {
        List<String> tokens = tokenize(text);
        int effectiveMax = maxLength - 2; // [CLS] + [SEP]
        if (tokens.size() > effectiveMax) {
            tokens = tokens.subList(0, effectiveMax);
        }

        long[] inputIds = new long[maxLength];
        long[] attentionMask = new long[maxLength];
        long[] tokenTypeIds = new long[maxLength];

        int idx = 0;
        inputIds[idx] = CLS_ID;
        attentionMask[idx] = 1;
        idx++;
        for (String token : tokens) {
            inputIds[idx] = idOf(token);
            attentionMask[idx] = 1;
            idx++;
        }
        inputIds[idx] = SEP_ID;
        attentionMask[idx] = 1;
        idx++;
        // 剩余位置保持 0（PAD）
        return new Tokens(inputIds, attentionMask, tokenTypeIds);
    }

    /** 默认 512 编码（对齐 sentence-transformers max_seq_length）。 */
    public Tokens encode(String text) {
        return encode(text, maxLength);
    }

    public int vocabSize() {
        return vocab.size();
    }

    public int maxLength() {
        return maxLength;
    }

    /** token → id（未知词 → [UNK]）。 */
    private long idOf(String token) {
        Integer id = vocab.get(token);
        return id == null ? UNK_ID : id;
    }

    /**
     * 基础分词：小写 → CJK 字符独立 → 按空白拆词 → WordPiece 子词。
     */
    List<String> tokenize(String text) {
        if (text == null || text.isBlank()) {
            return new ArrayList<>();
        }
        String lowered = text.toLowerCase();
        // 1. 在每个 CJK 字符两侧加空格（对齐 BasicTokenizer）
        StringBuilder spaced = new StringBuilder();
        for (int i = 0; i < lowered.length(); i++) {
            char c = lowered.charAt(i);
            if (isCjk(c)) {
                spaced.append(' ').append(c).append(' ');
            } else {
                spaced.append(c);
            }
        }
        // 2. 按空白拆词
        String[] words = spaced.toString().trim().split("\\s+");
        List<String> tokens = new ArrayList<>();
        for (String word : words) {
            if (word.isEmpty()) {
                continue;
            }
            tokens.addAll(wordPiece(word));
        }
        return tokens;
    }

    /** 对单个词做 WordPiece 子词切分（最长前缀匹配 + ## 续词）。 */
    private List<String> wordPiece(String word) {
        List<String> pieces = new ArrayList<>();
        int start = 0;
        while (start < word.length()) {
            int end = word.length();
            String sub = null;
            while (start < end) {
                String candidate = start == 0 ? word.substring(start, end) : "##" + word.substring(start, end);
                if (vocab.containsKey(candidate)) {
                    sub = candidate;
                    break;
                }
                end--;
            }
            if (sub == null) {
                pieces.add("[UNK]");
                start++; // 跳过无法匹配的字符
            } else {
                pieces.add(sub);
                start = end;
            }
            // 安全护栏：避免死循环
            if (end == start && sub == null) {
                start++;
            }
        }
        return pieces;
    }

    /** CJK 字符判断（对齐 Python transformers _is_chinese_char 的常见范围）。 */
    private boolean isCjk(char c) {
        int cp = c;
        return (cp >= 0x4E00 && cp <= 0x9FFF)
            || (cp >= 0x3400 && cp <= 0x4DBF)
            || (cp >= 0x20000 && cp <= 0x2A6DF)
            || (cp >= 0x2A700 && cp <= 0x2B73F)
            || (cp >= 0x2B740 && cp <= 0x2B81F)
            || (cp >= 0x2B820 && cp <= 0x2CEAF)
            || (cp >= 0xF900 && cp <= 0xFAFF)
            || (cp >= 0x2F800 && cp <= 0x2FA1F)
            || (cp >= 0x3000 && cp <= 0x303F) // CJK 标点
            || (cp >= 0xFF00 && cp <= 0xFFEF); // 全角
    }
}
