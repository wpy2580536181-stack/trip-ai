package com.trip.backend.web.filter;

import com.trip.backend.utils.AppException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 幂等 Filter（对应 Python middleware/idempotency.py）
 * - 仅作用于 /api/trip/recommend POST
 * - 进程内存存储（TTL 3600s，max 10000）
 * - key = {userId or anonymous}:{idempotency-key}
 * - 只缓存 2xx JSON 响应
 */
@Component
@Order(Ordered.LOWEST_PRECEDENCE - 4)
public class IdempotencyFilter extends OncePerRequestFilter {

    // 进程内存存储
    private final Map<String, Entry> cache = new ConcurrentHashMap<>();
    private static final long TTL_MS = 3600 * 1000L; // 3600s
    private static final int MAX_ENTRIES = 10000;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        // 仅作用于 /api/trip/recommend POST
        if (!"/api/trip/recommend".equals(request.getRequestURI())
            || !"POST".equalsIgnoreCase(request.getMethod())) {
            filterChain.doFilter(request, response);
            return;
        }

        // 提取幂等键
        String idempotencyKey = request.getHeader("X-Idempotency-Key");
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            filterChain.doFilter(request, response);
            return;
        }

        // 构建 cache key
        String userId = extractUserId(request);
        String cacheKey = (userId != null ? "user:" + userId : "anon") + ":" + idempotencyKey;

        // 检查缓存
        Entry entry = cache.get(cacheKey);
        long now = System.currentTimeMillis();
        if (entry != null && (now - entry.timestamp) < TTL_MS) {
            // 命中缓存，返回缓存响应
            response.setStatus(entry.statusCode);
            response.setContentType("application/json");
            response.getWriter().write(entry.responseBody);
            response.getWriter().flush();
            return;
        }

        // 包装 response 以捕获响应体
        CachedResponseWrapper wrappedResponse = new CachedResponseWrapper(response);

        try {
            filterChain.doFilter(request, wrappedResponse);

            // 缓存 2xx 响应
            if (wrappedResponse.getStatus() >= 200 && wrappedResponse.getStatus() < 300) {
                cache.put(cacheKey, new Entry(
                    wrappedResponse.getStatus(),
                    wrappedResponse.getCapturedBody(),
                    now
                ));
            }

            // 复制到原始 response
            wrappedResponse.copyBodyToResponse();

        } finally {
            // 清理超限条目（简化实现）
            if (cache.size() > MAX_ENTRIES) {
                cache.clear();
            }
        }
    }

    private String extractUserId(HttpServletRequest request) {
        // TODO: 从 SecurityContext 提取 userId
        return null;
    }

    private record Entry(int statusCode, String responseBody, long timestamp) {}

    /**
     * Response Wrapper（捕获响应体）
     */
    private static class CachedResponseWrapper extends jakarta.servlet.http.HttpServletResponseWrapper {
        private final java.io.ByteArrayOutputStream capturedBody = new java.io.ByteArrayOutputStream();
        private final jakarta.servlet.ServletOutputStream originalOutputStream;
        private final java.io.PrintWriter writer;

        CachedResponseWrapper(HttpServletResponse response) throws IOException {
            super(response);
            this.originalOutputStream = response.getOutputStream();
            this.writer = new java.io.PrintWriter(new java.io.OutputStreamWriter(capturedBody, response.getCharacterEncoding()), true);
        }

        @Override
        public void write(int b) throws IOException {
            capturedBody.write(b);
        }

        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            capturedBody.write(b, off, len);
        }

        @Override
        public void write(byte[] b) throws IOException {
            capturedBody.write(b);
        }

        @Override
        public jakarta.servlet.ServletOutputStream getOutputStream() {
            return new jakarta.servlet.ServletOutputStream() {
                @Override
                public void write(int b) {
                    capturedBody.write(b);
                }

                @Override
                public boolean isReady() {
                    return true;
                }

                @Override
                public void setWriteListener(jakarta.servlet.WriteListener writeListener) {}
            };
        }

        @Override
        public java.io.PrintWriter getWriter() {
            return writer;
        }

        @Override
        public void flushBuffer() throws IOException {
            writer.flush();
        }

        void copyBodyToResponse() throws IOException {
            byte[] body = capturedBody.toByteArray();
            response.setContentLength(body.length);
            response.getOutputStream().write(body);
            response.getOutputStream().flush();
        }

        int getStatus() {
            return ((HttpServletResponse) getResponse()).getStatus();
        }

        String getCapturedBody() {
            return capturedBody.toString();
        }
    }
}
