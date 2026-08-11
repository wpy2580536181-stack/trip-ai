package com.trip.backend.middleware;

import com.trip.backend.domain.entity.TokenUsageLog;
import com.trip.backend.domain.repository.TokenUsageLogRepository;
import dev.langchain4j.model.output.TokenUsage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Token 追踪回调（对应 Python token_tracker.py）
 * - 内存监控 + 预算检查
 * - token_usage_logs 异步落库（fire-and-forget）
 */
@Component
public class TokenTrackingCallback {

    private static final Logger log = LoggerFactory.getLogger(TokenTrackingCallback.class);

    private final TokenMonitor tokenMonitor;
    private final TokenBudgetManager tokenBudgetManager;
    private final TokenUsageLogRepository tokenUsageLogRepository;
    private final ExecutorService tokenLogExecutor;

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
        this.tokenLogExecutor = Executors.newSingleThreadExecutor(runnable -> {
            Thread thread = new Thread(runnable, "token-usage-log");
            thread.setDaemon(true);
            return thread;
        });
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

        int totalTokens = tokenUsage.totalTokenCount() != null ? tokenUsage.totalTokenCount() : 0;
        int promptTokens = tokenUsage.inputTokenCount() != null ? tokenUsage.inputTokenCount() : 0;
        int completionTokens = tokenUsage.outputTokenCount() != null ? tokenUsage.outputTokenCount() : 0;

        // 提取 cachedTokens（兼容不同字段名）
        Integer cachedTokens = null;
        try {
            // langchain4j 的 TokenUsage 可能没有 cachedTokens 字段
            // TODO: spike 后确认如何提取
        } catch (Exception e) {
            // 忽略
        }

        // 1. 监控器（使用本地 TokenUsage）
        com.trip.backend.middleware.TokenUsage usage = new com.trip.backend.middleware.TokenUsage(
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
        persistUsageAsync(usage);
    }

    private void persistUsageAsync(com.trip.backend.middleware.TokenUsage usage) {
        CompletableFuture.runAsync(() -> {
            try {
                TokenUsageLog entity = new TokenUsageLog(
                    usage.getUserId(),
                    usage.getRequestType(),
                    usage.getRoute(),
                    usage.getPromptTokens(),
                    usage.getCompletionTokens(),
                    usage.getTotalTokens(),
                    usage.getCachedTokens(),
                    usage.getLatencyMs()
                );
                tokenUsageLogRepository.save(entity);
            } catch (Exception e) {
                log.warn("Failed to persist token usage log for userId={}", usage.getUserId(), e);
            }
        }, tokenLogExecutor);
    }

    public static class TokenBudgetExceededException extends RuntimeException {
        public TokenBudgetExceededException(String message) {
            super(message);
        }
    }
}
