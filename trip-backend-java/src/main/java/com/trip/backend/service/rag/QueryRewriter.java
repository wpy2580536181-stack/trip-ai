package com.trip.backend.service.rag;

import java.util.*;
import java.util.regex.Pattern;

/**
 * 查询改写器
 *
 * 对应 Python services/rag/query_rewriter.py
 *
 * 功能：
 * - 提取关键词
 * - 移除停用词
 * - 城市前缀拼装
 */
public class QueryRewriter {

    // 中文停用词表
    private static final Set<String> STOP_WORDS_ZH = Set.of(
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
        "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "但", "从",
        "可以", "这个", "当", "本", "如", "就", "让", "把", "还", "用",
        "没", "能", "过", "她", "他", "它", "们", "那", "些", "什么",
        "怎么", "如何", "为什么", "哪", "吗", "呢", "吧", "啊", "嗯"
    );

    // 英文停用词表
    private static final Set<String> STOP_WORDS_EN = Set.of(
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "up", "about", "into", "over"
    );

    private static final Set<String> STOP_WORDS = new HashSet<>();
    static {
        STOP_WORDS.addAll(STOP_WORDS_ZH);
        STOP_WORDS.addAll(STOP_WORDS_EN);
    }

    // 城市正则
    private static final Pattern CITY_PATTERN = Pattern.compile(
        "(北京|上海|广州|深圳|成都|杭州|西安|南京|重庆|天津|武汉|苏州|厦门|昆明|三亚)"
    );

    /**
     * 提取关键词
     *
     * @param text 输入文本
     * @param maxKeywords 最大关键词数量
     * @return 关键词列表
     */
    public List<String> extractKeywords(String text, int maxKeywords) {
        // 简单分词：按空格、标点分割
        String[] words = text.toLowerCase().split("[\\s\\p{Punct}]+");

        // 过滤停用词和短词
        Set<String> seen = new LinkedHashSet<>();
        for (String word : words) {
            if (word.length() >= 2 && !STOP_WORDS.contains(word)) {
                seen.add(word);
            }
        }

        return new ArrayList<>(seen).subList(0, Math.min(seen.size(), maxKeywords));
    }

    /**
     * 改写查询
     *
     * @param query 原始查询
     * @param city 目标城市（可选）
     * @return 改写后的查询
     */
    public String rewriteQuery(String query, String city) {
        return rewriteQuery(query, city, null);
    }

    /**
     * 改写查询（带上下文）
     *
     * @param query 原始查询
     * @param city 目标城市（可选）
     * @param context 对话上下文（可选）
     * @return 改写后的查询
     */
    public String rewriteQuery(String query, String city, String context) {
        // 1. 清洗文本
        String cleaned = query.replaceAll("[^\\w\\s]", " ").replaceAll("\\s+", " ").trim();

        // 2. 提取关键词
        List<String> keywords = extractKeywords(cleaned, 10);

        // 3. 组装
        List<String> parts = new ArrayList<>();
        if (city != null && !city.isBlank() && !keywords.contains(city)) {
            parts.add(city);
        }
        parts.addAll(keywords);

        return String.join(" ", parts);
    }

    /**
     * 检测城市
     *
     * @param query 查询文本
     * @return 城市名（如果检测到）
     */
    public String detectCity(String query) {
        Matcher matcher = CITY_PATTERN.matcher(query);
        if (matcher.find()) {
            return matcher.group(1);
        }
        return null;
    }
}
