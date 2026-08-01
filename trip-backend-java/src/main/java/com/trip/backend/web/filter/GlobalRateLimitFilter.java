package com.trip.backend.web.filter;

import com.trip.backend.infra.ratelimit.RateLimitConfig;
import com.trip.backend.infra.ratelimit.RateLimiter;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 全局限流 Filter（对应 Python GlobalRateLimitMiddleware）
 * - 固定窗口算法
 * - 响应头：X-RateLimit-Limit / X-RateLimit-Remaining / X-RateLimit-Reset（绝对 Unix 时间戳）
 * - 仅作用于 /api 前缀
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 3)
public class GlobalRateLimitFilter extends OncePerRequestFilter {

    private final RateLimiter rateLimiter;

    public GlobalRateLimitFilter(RateLimiter rateLimiter) {
        this.rateLimiter = rateLimiter;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        // 仅作用于 /api 前缀
        String path = request.getRequestURI();
        if (path == null || !path.startsWith("/api/")) {
            filterChain.doFilter(request, response);
            return;
        }

        // 健康检查端点跳过限流
        if (path.startsWith("/health") || path.startsWith("/metrics")) {
            filterChain.doFilter(request, response);
            return;
        }

        // 确定限流类型
        RateLimitConfig config = determineRateLimitConfig(path);
        if (config == null) {
            filterChain.doFilter(request, response);
            return;
        }

        // 提取限流键（用户 ID 优先，否则 IP）
        String key = extractRateLimitKey(request);

        // 检查限流
        RateLimiter.RateLimitResult result = rateLimiter.check(key, config);

        // 设置响应头
        response.setHeader("X-RateLimit-Limit", String.valueOf(config.getMaxRequests()));
        response.setHeader("X-RateLimit-Remaining", String.valueOf(Math.max(0, config.getMaxRequests() - result.currentCount())));
        response.setHeader("X-RateLimit-Reset", String.valueOf(result.resetAt())); // 绝对 Unix 时间戳

        if (!result.allowed()) {
            // 超限，返回 429
            response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
            response.setContentType("application/json");
            response.getWriter().write("{\"detail\":\"Too many requests\"}");
            return;
        }

        filterChain.doFilter(request, response);
    }

    /**
     * 根据路径确定限流类型
     */
    private RateLimitConfig determineRateLimitConfig(String path) {
        if (path.startsWith("/api/user/")) {
            return RateLimitConfig.AUTH;
        } else if (path.startsWith("/api/trip/chat")) {
            return RateLimitConfig.CHAT;
        } else if (path.startsWith("/api/trip/recommend")) {
            return RateLimitConfig.RECOMMEND;
        } else if (path.startsWith("/api/feedback")) {
            return RateLimitConfig.FEEDBACK;
        } else if (path.startsWith("/api/knowledge/")) {
            return RateLimitConfig.KNOWLEDGE;
        } else if (path.startsWith("/api/")) {
            return RateLimitConfig.GLOBAL;
        }
        return null;
    }

    /**
     * 提取限流键
     */
    private String extractRateLimitKey(HttpServletRequest request) {
        // TODO: 从 JWT 或 session 提取 userId
        // 暂时返回 IP
        return request.getRemoteAddr();
    }
}
