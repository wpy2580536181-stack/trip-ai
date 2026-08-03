package com.trip.backend.eval.types;

import java.util.Map;

/**
 * 报告汇总
 */
public class ReportSummary {
    private int totalFixtures = 0;
    private int passedFixtures = 0;
    private int failedFixtures = 0;
    private long totalDurationMs = 0;
    private double passRate = 0.0;
    private Map<String, GroupStats> byTag = Map.of();
    private Map<String, GroupStats> byEvaluator = Map.of();
    private TokenUsage totalTokens;

    public ReportSummary() {
    }

    public ReportSummary(int totalFixtures, int passedFixtures, int failedFixtures, long totalDurationMs, double passRate, Map<String, GroupStats> byTag, Map<String, GroupStats> byEvaluator, TokenUsage totalTokens) {
        this.totalFixtures = totalFixtures;
        this.passedFixtures = passedFixtures;
        this.failedFixtures = failedFixtures;
        this.totalDurationMs = totalDurationMs;
        this.passRate = passRate;
        this.byTag = byTag;
        this.byEvaluator = byEvaluator;
        this.totalTokens = totalTokens;
    }

    public int getTotalFixtures() {
        return totalFixtures;
    }

    public void setTotalFixtures(int totalFixtures) {
        this.totalFixtures = totalFixtures;
    }

    public int getPassedFixtures() {
        return passedFixtures;
    }

    public void setPassedFixtures(int passedFixtures) {
        this.passedFixtures = passedFixtures;
    }

    public int getFailedFixtures() {
        return failedFixtures;
    }

    public void setFailedFixtures(int failedFixtures) {
        this.failedFixtures = failedFixtures;
    }

    public long getTotalDurationMs() {
        return totalDurationMs;
    }

    public void setTotalDurationMs(long totalDurationMs) {
        this.totalDurationMs = totalDurationMs;
    }

    public double getPassRate() {
        return passRate;
    }

    public void setPassRate(double passRate) {
        this.passRate = passRate;
    }

    public Map<String, GroupStats> getByTag() {
        return byTag;
    }

    public void setByTag(Map<String, GroupStats> byTag) {
        this.byTag = byTag;
    }

    public Map<String, GroupStats> getByEvaluator() {
        return byEvaluator;
    }

    public void setByEvaluator(Map<String, GroupStats> byEvaluator) {
        this.byEvaluator = byEvaluator;
    }

    public TokenUsage getTotalTokens() {
        return totalTokens;
    }

    public void setTotalTokens(TokenUsage totalTokens) {
        this.totalTokens = totalTokens;
    }
}
