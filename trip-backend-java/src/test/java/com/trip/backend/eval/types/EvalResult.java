package com.trip.backend.eval.types;

import java.util.Map;

/**
 * 单个 evaluator 评分结果
 */
public class EvalResult {
    private boolean passed;
    private String reason = "";
    private Map<String, Object> details = Map.of();

    public EvalResult() {
    }

    public EvalResult(boolean passed, String reason, Map<String, Object> details) {
        this.passed = passed;
        this.reason = reason;
        this.details = details;
    }

    public boolean isPassed() {
        return passed;
    }

    public void setPassed(boolean passed) {
        this.passed = passed;
    }

    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public Map<String, Object> getDetails() {
        return details;
    }

    public void setDetails(Map<String, Object> details) {
        this.details = details;
    }

    public static EvalResult fail(String reason) {
        return new EvalResult(false, reason, Map.of());
    }

    public static EvalResult pass() {
        return new EvalResult(true, "", Map.of());
    }

    public static EvalResult pass(String reason) {
        return new EvalResult(true, reason, Map.of());
    }

    public static EvalResult pass(Map<String, Object> details) {
        return new EvalResult(true, "", details);
    }
}
