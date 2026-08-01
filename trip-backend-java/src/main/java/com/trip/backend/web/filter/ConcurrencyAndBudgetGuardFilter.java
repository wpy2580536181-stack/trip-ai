package com.trip.backend.web.filter;

import com.trip.backend.middleware.ConcurrencyGuard;
import com.trip.backend.middleware.TokenBudgetManager;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 并发 + Token 预算守卫 Filter（对应 Python middleware/concurrency_guard.py + token_budget_guard.py）
 * - 并发：全局 10 / 每用户 1（超限 429）
 * - Token：用户 50K/h → 429 / 全局 200K/min → 503
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 5)
public class ConcurrencyAndBudgetGuardFilter extends OncePerRequestFilter {

    private final ConcurrencyGuard concurrencyGuard;
    private final TokenBudgetManager tokenBudgetManager;

    public ConcurrencyAndBudgetGuardFilter(ConcurrencyGuard concurrencyGuard,
                                          TokenBudgetManager tokenBudgetManager) {
        this.concurrencyGuard = concurrencyGuard;
        this.tokenBudgetManager = tokenBudgetManager;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();

        // 仅作用于 chat 和 recommend 端点
        boolean isChat = path.startsWith("/api/trip/chat");
        boolean isRecommend = path.startsWith("/api/trip/recommend");
        if (!isChat && !isRecommend) {
            filterChain.doFilter(request, response);
            return;
        }

        // 提取 userId
        Long userId = extractUserId(request);

        try {
            // 1. 并发守卫
            concurrencyGuard.acquire(userId);

            try {
                // 2. Token 预算守卫（用户）
                // TODO: 从请求中提取 token 数量（需 LLM 调用后记账）
                // 暂时跳过，后续在 D2 任务中完善
                // TokenBudgetManager.BudgetResult userBudget = tokenBudgetManager.checkUser(userId, estimatedTokens);
                // if (!userBudget.allowed()) {
                //     response.sendError(429, "User token budget exceeded");
                //     return;
                // }

                // 3. Token 预算守卫（全局）
                // TokenBudgetManager.BudgetResult globalBudget = tokenBudgetManager.checkGlobal(estimatedTokens);
                // if (!globalBudget.allowed()) {
                //     response.sendError(503, "Global token budget exceeded");
                //     return;
                // }

                filterChain.doFilter(request, response);

            } finally {
                concurrencyGuard.release(userId);
            }

        } catch (ConcurrencyGuard.ConcurrencyLimitException e) {
            response.sendError(429, "Too many concurrent requests");
        }
    }

    private Long extractUserId(HttpServletRequest request) {
        // TODO: 从 SecurityContext 提取
        return null;
    }
}
