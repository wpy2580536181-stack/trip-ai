package com.trip.backend.web.filter;

import com.trip.backend.middleware.ConcurrencyGuard;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 并发守卫 Filter（对应 Python concurrency_guard middleware）
 * - 仅拦截 SSE/流式 AI 端点（chat/recommend-stream）
 * - 全局并发 Semaphore(10)，超限返回 429
 * - 用户级 Semaphore(1)，同一用户并发流式请求超限返回 429
 */
@Component
public class ConcurrencyGuardFilter extends OncePerRequestFilter {

    private final ConcurrencyGuard guard;

    public ConcurrencyGuardFilter(ConcurrencyGuard guard) {
        this.guard = guard;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        String method = request.getMethod();
        // 仅保护 POST 流式 AI 端点
        boolean isStreamEndpoint = "/api/trip/chat".equals(path)
                || "/api/trip/recommend-stream".equals(path);
        return !isStreamEndpoint || !"POST".equals(method);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        Long userId = (Long) request.getAttribute("userId");
        boolean acquired;
        try {
            guard.acquire(userId);
            acquired = true;
        } catch (ConcurrencyGuard.ConcurrencyLimitException e) {
            acquired = false;
        }

        if (!acquired) {
            response.setStatus(429);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"code\":429,\"message\":\"" +
                    "服务器繁忙，请稍后重试\",\"error\":\"Too Many Requests\"}");
            return;
        }

        try {
            chain.doFilter(request, response);
        } finally {
            guard.release(userId);
        }
    }
}
