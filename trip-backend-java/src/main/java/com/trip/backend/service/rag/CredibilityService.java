package com.trip.backend.service.rag;

import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Map;

/**
 * 可信度服务
 *
 * 对应 Python services/rag/credibility.py
 *
 * 功能：
 * - 5 维评分：authority/freshness/agreement/citation/evidence
 * - freshness 30/365 天线性衰减
 * - AUTHORITY_DEFAULTS 表
 */
@Service
public class CredibilityService {

    // 可信度维度权重
    private static final double WEIGHT_AUTHORITY = 0.25;
    private static final double WEIGHT_FRESHNESS = 0.20;
    private static final double WEIGHT_AGREEMENT = 0.25;
    private static final double WEIGHT_CITATION = 0.15;
    private static final double WEIGHT_EVIDENCE = 0.15;

    // 新鲜度衰减参数
    private static final long FRESHNESS_HALF_LIFE_DAYS = 30;
    private static final long MAX_AGE_DAYS = 365;

    /**
     * 计算可信度综合分（0-1）
     *
     * @param authority 权威性（0-1）
     * @param createdAt 创建时间（epoch 秒）
     * @param agreement 一致性（0-1）
     * @param citation 引用数
     * @param evidence 证据质量（0-1）
     * @return 综合可信度（0-1）
     */
    public double calculateCredibility(double authority, long createdAt, double agreement, int citation, double evidence) {
        double freshness = calculateFreshness(createdAt);
        double citationScore = normalizeCitation(citation);

        return WEIGHT_AUTHORITY * authority
            + WEIGHT_FRESHNESS * freshness
            + WEIGHT_AGREEMENT * agreement
            + WEIGHT_CITATION * citationScore
            + WEIGHT_EVIDENCE * evidence;
    }

    /**
     * 计算新鲜度（线性衰减）
     *
     * @param createdAt 创建时间（epoch 秒）
     * @return 新鲜度（0-1）
     */
    public double calculateFreshness(long createdAt) {
        long ageDays = (Instant.now().getEpochSecond() - createdAt) / 86400;

        if (ageDays <= 0) {
            return 1.0;
        }

        if (ageDays >= MAX_AGE_DAYS) {
            return 0.0;
        }

        // 线性衰减
        return 1.0 - (double) ageDays / MAX_AGE_DAYS;
    }

    /**
     * 归一化引用数（0-1）
     *
     * @param citation 引用数
     * @return 归一化分数（0-1）
     */
    private double normalizeCitation(int citation) {
        if (citation <= 0) {
            return 0.0;
        }

        // 对数归一化：log10(citation + 1) / log10(101)
        return Math.log10(citation + 1) / Math.log10(101);
    }

    /**
     * 获取权威性默认值
     *
     * @param sourceType 来源类型
     * @return 权威性（0-1）
     */
    public double getDefaultAuthority(String sourceType) {
        // AUTHORITY_DEFAULTS 映射（简化版）
        return switch (sourceType != null ? sourceType.toLowerCase() : "") {
            case "official" -> 0.9;
            case "guidebook" -> 0.7;
            case "user_review" -> 0.5;
            case "social_media" -> 0.4;
            default -> 0.5;
        };
    }
}
