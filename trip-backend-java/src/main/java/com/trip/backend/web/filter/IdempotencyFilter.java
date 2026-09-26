package com.trip.backend.web.filter;

import org.springframework.beans.factory.annotation.Autowired;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingResponseWrapper;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 幂等性 Filter（对应 Python src/middleware/idempotency.py）
 *
 * - 仅对 POST /api/trip/recommend 生效（精确路径；/recommend-stream 等 SSE 路径不受影响）
 * - 相同 Idempotency-Key 重复请求返回缓存响应，响应体与首次逐字节相同
 * - key = {userId 或 anonymous}:{Idempotency-Key 头}
 * - 进程内存缓存，TTL 3600s（惰性过期）
 * - 只缓存 2xx 且为 JSON 的响应；非 JSON / 非 2xx 不缓存
 * - 命中时直接返回缓存体（原响应头丢失——保持 Python 行为，不补头）
 *
 * 注册顺序见 FilterOrderConfig（order=5，限流之后）。
 */
@Component
public class IdempotencyFilter extends OncePerRequestFilter {

    public static final String IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";
    public static final String TARGET_PATH = "/api/trip/recommend";
    public static final long DEFAULT_TTL_SECONDS = 3600;

    private final ConcurrentHashMap<String, CachedResponse> store = new ConcurrentHashMap<>();
    private final long ttlSeconds;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public IdempotencyFilter() {
        this(DEFAULT_TTL_SECONDS);
    }

    /** @param ttlSeconds 缓存 TTL（秒），测试可用短 TTL 验证过期行为 */
    public IdempotencyFilter(long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }

    /** 缓存的响应（对应 Python CachedResponse）。 */
    record CachedResponse(int statusCode, String body, long createdAtMillis) {
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        // 仅拦截 POST /api/trip/recommend
        if (!"POST".equalsIgnoreCase(request.getMethod())
                || !TARGET_PATH.equals(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }

        String rawKey = request.getHeader(IDEMPOTENCY_KEY_HEADER);
        if (rawKey == null || rawKey.isBlank()) {
            filterChain.doFilter(request, response);
            return;
        }

        String fullKey = buildKey(request, rawKey);

        // 命中缓存 → 直接返回（不补响应头，保持 Python 行为）
        CachedResponse cached = getIfFresh(fullKey);
        if (cached != null) {
            response.setStatus(cached.statusCode());
            response.setContentType("application/json");
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(cached.body());
            return;
        }

        // 未命中 → 执行请求并捕获响应体，2xx 且 JSON 才缓存
        ContentCachingResponseWrapper wrapper = new ContentCachingResponseWrapper(response);
        try {
            filterChain.doFilter(request, wrapper);
        } finally {
            int statusCode = wrapper.getStatus();
            if (statusCode >= 200 && statusCode < 300) {
                String body = new String(wrapper.getContentAsByteArray(), StandardCharsets.UTF_8);
                if (isValidJson(body)) {
                    store.put(fullKey, new CachedResponse(statusCode, body, System.currentTimeMillis()));
                }
            }
            // 把缓存的内容写回真实响应（含非 2xx / 非 JSON 场景）
            wrapper.copyBodyToResponse();
        }
    }

    private String buildKey(HttpServletRequest request, String rawKey) {
        Object userId = request.getAttribute("userId");
        String userPart = (userId instanceof Number)
            ? String.valueOf(((Number) userId).longValue())
            : "anonymous";
        return userPart + ":" + rawKey;
    }

    /** 惰性过期读取：过期条目删除并视为未命中（对应 Python MemoryIdempotencyStore.get）。 */
    private CachedResponse getIfFresh(String key) {
        CachedResponse entry = store.get(key);
        if (entry == null) {
            return null;
        }
        if (System.currentTimeMillis() - entry.createdAtMillis() >= ttlSeconds * 1000L) {
            store.remove(key, entry);
            return null;
        }
        return entry;
    }

    private boolean isValidJson(String body) {
        if (body == null || body.isBlank()) {
            return false;
        }
        try {
            objectMapper.readTree(body);
            return true;
        } catch (Exception e) {
            return false;
        }
    }
}
