package com.trip.backend.service.rag;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 本地查询改写（对应 Python src/services/rag/query_rewriter.py）。
 *
 * - 去标点：保留中文/英文/数字/空格
 * - 提取关键词：中英停用词过滤、len≥2、去重保序（max_keywords=10）
 * - city 前缀拼装：city 不在关键词中时前置
 *
 * 注：Java \w 默认不含中文，必须启用 UNICODE_CHARACTER_CLASS 才能与 Python 行为一致。
 */
@Component
public class QueryRewriter {

    private static final Pattern WORD_PATTERN = Pattern.compile("[\\w]+", Pattern.UNICODE_CHARACTER_CLASS);
    private static final Pattern CLEAN_PATTERN = Pattern.compile("[^\\w\\s]", Pattern.UNICODE_CHARACTER_CLASS);

    /** 中文停用词表（与 Python _STOP_WORDS_ZH 一致）。 */
    private static final Set<String> STOP_WORDS_ZH = Set.of(
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "但", "从",
        "可以", "这个", "当", "本", "如", "让", "把", "还", "用",
        "没", "能", "过", "她", "他", "它", "们", "那", "些", "什么",
        "怎么", "如何", "为什么", "哪", "吗", "呢", "吧", "啊", "嗯"
    );

    /** 英文停用词表（与 Python _STOP_WORDS_EN 一致）。 */
    private static final Set<String> STOP_WORDS_EN = Set.of(
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "up", "about", "into", "over",
        "after", "beneath", "between", "under", "i", "me", "my", "we",
        "you", "he", "she", "it", "they", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "shall", "should", "can", "could", "may", "might"
    );

    private static final Set<String> STOP_WORDS;
    private static final int MAX_KEYWORDS = 10;

    static {
        Set<String> all = new java.util.HashSet<>(STOP_WORDS_ZH);
        all.addAll(STOP_WORDS_EN);
        STOP_WORDS = Set.copyOf(all);
    }

    /**
     * 从文本提取关键词（分词 + 停用词过滤 + 去重保序）。
     *
     * @param text         输入文本
     * @param maxKeywords  最大关键词数量
     */
    public List<String> extractKeywords(String text, int maxKeywords) {
        if (text == null || text.isBlank()) {
            return List.of();
        }
        Matcher matcher = WORD_PATTERN.matcher(text.toLowerCase());
        List<String> keywords = new ArrayList<>();
        while (matcher.find()) {
            String word = matcher.group();
            if (!STOP_WORDS.contains(word) && word.length() >= 2) {
                keywords.add(word);
            }
        }
        // 去重并保持顺序
        Set<String> seen = new LinkedHashSet<>(keywords);
        return seen.stream().limit(maxKeywords).toList();
    }

    public List<String> extractKeywords(String text) {
        return extractKeywords(text, MAX_KEYWORDS);
    }

    /**
     * 本地查询改写（不调用 LLM）。
     *
     * @param query   原始查询
     * @param city    目标城市（可选，前置拼装）
     * @param context 对话上下文（预留，暂未使用）
     */
    public String rewrite(String query, String city, String context) {
        if (query == null) {
            return "";
        }
        // 1. 清洗文本：保留中文、英文、数字、空格
        String cleaned = CLEAN_PATTERN.matcher(query).replaceAll(" ");
        cleaned = cleaned.replaceAll("\\s+", " ").trim();

        // 2. 提取关键词
        List<String> keywords = extractKeywords(cleaned);

        // 3. 组装改写后的查询
        List<String> parts = new ArrayList<>();
        if (city != null && !city.isBlank() && !keywords.contains(city)) {
            parts.add(city);
        }
        parts.addAll(keywords);

        String rewritten = parts.isEmpty() ? cleaned : String.join(" ", parts);
        return rewritten;
    }
}
