package com.trip.backend.web.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

/**
 * Request ID Filter（对应 Python RequestIDMiddleware）
 * - 透传 x-request-id（如客户端已提供）
 * - 否则生成新的 UUID
 * - 响应头回写 x-request-id
 * - 绑定到 MDC（用于日志）
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID_HEADER = "x-request-id";
    public static final String MDC_KEY = "requestId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        try {
            // 1. 获取或生成 Request ID
            String requestId = request.getHeader(REQUEST_ID_HEADER);
            if (requestId == null || requestId.isBlank()) {
                requestId = UUID.randomUUID().toString();
            }

            // 2. 回写到响应头
            response.setHeader(REQUEST_ID_HEADER, requestId);

            // 3. 绑定到 MDC
            org.slf4j.MDC.put(MDC_KEY, requestId);

            // 4. 继续过滤器链
            filterChain.doFilter(request, response);
        } finally {
            // 5. 清理 MDC
            org.slf4j.MDC.remove(MDC_KEY);
        }
    }
}
