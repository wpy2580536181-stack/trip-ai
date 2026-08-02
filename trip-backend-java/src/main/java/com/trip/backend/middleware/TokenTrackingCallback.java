package com.trip.backend.middleware;

import dev.langchain4j.model.output.TokenUsage;
import org.springframework.stereotype.Component;

/**
 * Token 追踪回调（对应 Python token_tracker.py）
 */
@Component
public class TokenTrackingCallback {

    private final TokenMonitor tokenMonitor;
    private final TokenBudgetManager tokenBudgetManager;
    private final TokenUsageLogRepository tokenUsageLogRepository;

    // ThreadLocal 上下文
    private static final ThreadLocal<Long> currentUserId = new ThreadLocal<>();
    private static final ThreadLocal<String> currentRequestType = new ThreadLocal<>();
    private static final ThreadLocal<String> currentRoute = new ThreadLocal<>();

    public TokenTrackingCallback(TokenMonitor tokenMonitor,
                                TokenBudgetManager tokenBudgetManager,
                                TokenUsageLogRepository tokenUsageLogRepository) {
        this.tokenMonitor = tokenMonitor;
        this.tokenBudgetManager = tokenBudgetManager;
        this.tokenUsageLogRepository = tokenUsageLogRepository;
    }

    /**
     * 设置上下文
     */
    public void setContext(Long userId, String requestType, String route) {
        currentUserId.set(userId);
        currentRequestType.set(requestType);
        currentRoute.set(route);
    }

    /**
     * 清理上下文
     */
    public void clearContext() {
        currentUserId.remove();
        currentRequestType.remove();
        currentRoute.remove();
    }

    /**
     * 记录 LLM token 使用
     */
    public void recordLlmUsage(TokenUsage tokenUsage, long latencyMs) {
        Long userId = currentUserId.get();
        if (userId == null || tokenUsage == null) {
            return;
        }

        int totalTokens = tokenUsage.totalTokenCount();
        int promptTokens = tokenUsage.inputTokenCount();
        int completionTokens = tokenUsage.outputTokenCount();

        // 提取 cachedTokens（兼容不同字段名）
        Integer cachedTokens = null;
        try {
            // langchain4j 的 TokenUsage 可能没有 cachedTokens 字段
            // TODO: spike 后确认如何提取
        } catch (Exception e) {
            // 忽略
        }

        // 1. 监控器
        TokenUsage usage = new TokenUsage(
            userId,
            currentRequestType.get() != null ? currentRequestType.get() : "unknown",
            currentRoute.get() != null ? currentRoute.get() : "unknown",
            promptTokens,
            completionTokens,
            totalTokens,
            cachedTokens,
            (int) latencyMs
        );
        tokenMonitor.record(usage);

        // 2. 预算检查
        TokenBudgetManager.BudgetResult userBudget = tokenBudgetManager.checkUser(userId, totalTokens);
        if (!userBudget.allowed()) {
            throw new TokenBudgetExceededException("User token budget exceeded");
        }

        TokenBudgetManager.BudgetResult globalBudget = tokenBudgetManager.checkGlobal(totalTokens);
        if (!globalBudget.allowed()) {
            throw new TokenBudgetExceededException("Global token budget exceeded");
        }

        // 3. 异步落库（fire-and-forget）
        // TODO: 实现异步写入 token_usage_logs
    }

    public static class TokenBudgetExceededException extends RuntimeException {
        public TokenBudgetExceededException(String message) {
            super(message);
        }
    }
}
