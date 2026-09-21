package com.trip.backend.test.unit;

import com.trip.backend.web.filter.IdempotencyFilter;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

/**
 * J-B7x IdempotencyFilter 单元测试。
 * 验证：相同 Idempotency-Key 二次请求响应逐字节相同、TTL 过期重放、仅 /api/trip/recommend 生效。
 */
class IdempotencyFilterTest {

    private static final String JSON_BODY = "{\"success\":true,\"id\":1,\"city\":\"成都\"}";

    private final AtomicInteger chainCalls = new AtomicInteger();

    private FilterChain jsonChain() {
        return (req, res) -> {
            chainCalls.incrementAndGet();
            jakarta.servlet.http.HttpServletResponse httpRes = (jakarta.servlet.http.HttpServletResponse) res;
            httpRes.setStatus(200);
            httpRes.setContentType("application/json");
            httpRes.setCharacterEncoding("UTF-8");
            httpRes.getWriter().write(JSON_BODY);
        };
    }

    private MockHttpServletRequest post(String path, String key, Long userId) {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", path);
        if (key != null) {
            request.addHeader("Idempotency-Key", key);
        }
        if (userId != null) {
            request.setAttribute("userId", userId);
        }
        return request;
    }

    @Test
    void sameKeyReturnsByteIdenticalBodyAndSkipsChain() throws Exception {
        IdempotencyFilter filter = new IdempotencyFilter(3600);
        FilterChain chain = jsonChain();

        // 第一次请求：执行并缓存
        MockHttpServletResponse first = new MockHttpServletResponse();
        filter.doFilter(post("/api/trip/recommend", "k1", 42L), first, chain);
        assertEquals(1, chainCalls.get());

        // 第二次相同 key：直接返回缓存，链不再执行
        MockHttpServletResponse second = new MockHttpServletResponse();
        filter.doFilter(post("/api/trip/recommend", "k1", 42L), second, chain);
        assertEquals(1, chainCalls.get(), "重复请求不应再次执行下游");

        // 响应体逐字节相同
        assertEquals(first.getContentAsString(), second.getContentAsString());
        assertEquals(JSON_BODY, second.getContentAsString());
        assertEquals(200, second.getStatus());
    }

    @Test
    void ttlExpiryReplaysRequest() throws Exception {
        IdempotencyFilter filter = new IdempotencyFilter(1); // 1s TTL
        FilterChain chain = jsonChain();

        MockHttpServletResponse first = new MockHttpServletResponse();
        filter.doFilter(post("/api/trip/recommend", "k-exp", 42L), first, chain);
        assertEquals(1, chainCalls.get());

        Thread.sleep(1100); // 等待 TTL 过期

        MockHttpServletResponse second = new MockHttpServletResponse();
        filter.doFilter(post("/api/trip/recommend", "k-exp", 42L), second, chain);
        assertEquals(2, chainCalls.get(), "TTL 过期后应重新执行");
        assertEquals(JSON_BODY, second.getContentAsString());
    }

    @Test
    void noEffectOnOtherPaths() throws Exception {
        IdempotencyFilter filter = new IdempotencyFilter(3600);
        FilterChain chain = jsonChain();

        // /api/trip/chat 完全不生效：两次都执行
        filter.doFilter(post("/api/trip/chat", "k1", 42L), new MockHttpServletResponse(), chain);
        filter.doFilter(post("/api/trip/chat", "k1", 42L), new MockHttpServletResponse(), chain);
        assertEquals(2, chainCalls.get(), "chat 路径不应启用幂等");

        // /api/trip/recommend-stream（SSE）也不生效
        filter.doFilter(post("/api/trip/recommend-stream", "k1", 42L), new MockHttpServletResponse(), chain);
        filter.doFilter(post("/api/trip/recommend-stream", "k1", 42L), new MockHttpServletResponse(), chain);
        assertEquals(4, chainCalls.get(), "recommend-stream 不应启用幂等");
    }

    @Test
    void noEffectWithoutIdempotencyKeyOrOnGet() throws Exception {
        IdempotencyFilter filter = new IdempotencyFilter(3600);
        FilterChain chain = jsonChain();

        // 无 Idempotency-Key 头 → 放行
        filter.doFilter(post("/api/trip/recommend", null, 42L), new MockHttpServletResponse(), chain);
        assertEquals(1, chainCalls.get());

        // GET 请求 → 放行
        MockHttpServletRequest get = new MockHttpServletRequest("GET", "/api/trip/recommend");
        get.addHeader("Idempotency-Key", "k1");
        get.setAttribute("userId", 42L);
        filter.doFilter(get, new MockHttpServletResponse(), chain);
        assertEquals(2, chainCalls.get());
    }

    @Test
    void differentUserOrKeyDoesNotShareCache() throws Exception {
        IdempotencyFilter filter = new IdempotencyFilter(3600);
        FilterChain chain = jsonChain();

        filter.doFilter(post("/api/trip/recommend", "k1", 1L), new MockHttpServletResponse(), chain);
        // 不同用户相同 key → 重新执行
        filter.doFilter(post("/api/trip/recommend", "k1", 2L), new MockHttpServletResponse(), chain);
        // 相同用户不同 key → 重新执行
        filter.doFilter(post("/api/trip/recommend", "k2", 1L), new MockHttpServletResponse(), chain);
        assertEquals(3, chainCalls.get(), "userId 或 key 不同不应命中缓存");
    }

    @Test
    void nonJsonOrNon2xxResponseNotCached() throws Exception {
        IdempotencyFilter filter = new IdempotencyFilter(3600);

        // 非 JSON 响应不缓存（两次都执行）
        FilterChain plainChain = (req, res) -> {
            chainCalls.incrementAndGet();
            jakarta.servlet.http.HttpServletResponse httpRes = (jakarta.servlet.http.HttpServletResponse) res;
            httpRes.setStatus(200);
            httpRes.setContentType("text/plain");
            httpRes.getWriter().write("plain text");
        };
        filter.doFilter(post("/api/trip/recommend", "k-json", 42L), new MockHttpServletResponse(), plainChain);
        filter.doFilter(post("/api/trip/recommend", "k-json", 42L), new MockHttpServletResponse(), plainChain);
        assertEquals(2, chainCalls.get(), "非 JSON 响应不应缓存");

        // 非 2xx 响应不缓存（两次都执行）
        FilterChain errorChain = (req, res) -> {
            chainCalls.incrementAndGet();
            jakarta.servlet.http.HttpServletResponse httpRes = (jakarta.servlet.http.HttpServletResponse) res;
            httpRes.setStatus(500);
            httpRes.setContentType("application/json");
            httpRes.getWriter().write("{\"detail\":\"boom\"}");
        };
        filter.doFilter(post("/api/trip/recommend", "k-err", 42L), new MockHttpServletResponse(), errorChain);
        filter.doFilter(post("/api/trip/recommend", "k-err", 42L), new MockHttpServletResponse(), errorChain);
        assertEquals(4, chainCalls.get(), "非 2xx 响应不应缓存");

        // 响应体确实写回（500 场景 body 不丢）
        MockHttpServletResponse errorResp = new MockHttpServletResponse();
        filter.doFilter(post("/api/trip/recommend", "k-err2", 42L), errorResp, errorChain);
        assertNotEquals(0, errorResp.getContentAsString().length(), "错误响应体不应丢失");
    }
}
