package com.trip.backend.eval.types;

import java.util.List;

/**
 * 工具调用规则
 */
public class ToolCallRule {
    private String name;
    private int minCalls = 0;
    private int maxCalls = -1;

    public ToolCallRule() {
    }

    public ToolCallRule(String name, int minCalls, int maxCalls) {
        this.name = name;
        this.minCalls = minCalls;
        this.maxCalls = maxCalls;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getMinCalls() {
        return minCalls;
    }

    public void setMinCalls(int minCalls) {
        this.minCalls = minCalls;
    }

    public int getMaxCalls() {
        return maxCalls;
    }

    public void setMaxCalls(int maxCalls) {
        this.maxCalls = maxCalls;
    }
}
