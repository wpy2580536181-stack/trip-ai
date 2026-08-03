package com.trip.backend.eval.types;

/**
 * Token 消耗统计
 */
public class TokenUsage {
    private int prompt = 0;
    private int completion = 0;
    private int total = 0;
    private int cached = 0;

    public TokenUsage() {
    }

    public TokenUsage(int prompt, int completion, int total, int cached) {
        this.prompt = prompt;
        this.completion = completion;
        this.total = total;
        this.cached = cached;
    }

    public int getPrompt() {
        return prompt;
    }

    public void setPrompt(int prompt) {
        this.prompt = prompt;
    }

    public int getCompletion() {
        return completion;
    }

    public void setCompletion(int completion) {
        this.completion = completion;
    }

    public int getTotal() {
        return total;
    }

    public void setTotal(int total) {
        this.total = total;
    }

    public int getCached() {
        return cached;
    }

    public void setCached(int cached) {
        this.cached = cached;
    }

    public double getCacheHitRate() {
        return prompt > 0 ? (double) cached / prompt : 0.0;
    }
}
