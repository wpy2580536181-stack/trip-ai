package com.trip.backend.eval.types;

/**
 * 分组统计（按 tag 或 evaluator）
 */
public class GroupStats {
    public int passed = 0;
    public int total = 0;

    public GroupStats() {
    }

    public GroupStats(int passed, int total) {
        this.passed = passed;
        this.total = total;
    }

    public int getPassed() {
        return passed;
    }

    public void setPassed(int passed) {
        this.passed = passed;
    }

    public int getTotal() {
        return total;
    }

    public void setTotal(int total) {
        this.total = total;
    }

    public double getPassRate() {
        return total > 0 ? (double) passed / total : 0.0;
    }
}
