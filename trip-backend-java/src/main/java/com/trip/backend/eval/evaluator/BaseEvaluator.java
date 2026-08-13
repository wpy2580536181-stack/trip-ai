package com.trip.backend.eval.evaluator;

import com.trip.backend.eval.types.AgentOutput;

import java.util.List;

/**
 * Evaluator 基类（简化版）
 */
public abstract class BaseEvaluator {

    protected String name;

    protected BaseEvaluator(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    /**
     * 执行评估，返回是否通过
     */
    public abstract boolean evaluate(AgentOutput agentOutput);

    /**
     * 获取失败原因
     */
    public String getReason() {
        return "";
    }

    /**
     * 检查文本是否包含关键词
     */
    protected boolean containsKeyword(String text, String keyword) {
        return text != null && text.contains(keyword);
    }

    /**
     * 检查文本是否包含所有关键词
     */
    protected boolean containsAllKeywords(String text, List<String> keywords) {
        if (keywords == null || keywords.isEmpty()) return true;
        for (String kw : keywords) {
            if (!containsKeyword(text, kw)) return false;
        }
        return true;
    }

    /**
     * 检查文本是否不包含禁止关键词
     */
    protected boolean notContainsKeywords(String text, List<String> keywords) {
        if (keywords == null || keywords.isEmpty()) return true;
        for (String kw : keywords) {
            if (containsKeyword(text, kw)) return false;
        }
        return true;
    }
}
