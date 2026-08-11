package com.trip.backend.test.unit;

import com.trip.backend.infra.ratelimit.RateLimitConfig;
import com.trip.backend.infra.ratelimit.RateLimiter;
import com.trip.backend.web.filter.GlobalRateLimitFilter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GlobalRateLimitFilterTest {

    private final RateLimiter rateLimiter = mock(RateLimiter.class);
    private final GlobalRateLimitFilter filter = new GlobalRateLimitFilter(rateLimiter);
    private final HttpServletRequest request = mock(HttpServletRequest.class);
    private final HttpServletResponse response = mock(HttpServletResponse.class);
    private final FilterChain chain = mock(FilterChain.class);

    @Test
    void usesUserIdWhenRequestAttributeIsPresent() throws Exception {
        when(request.getRequestURI()).thenReturn("/api/trip/chat");
        when(request.getAttribute("userId")).thenReturn(42L);
        when(rateLimiter.check(anyString(), eq(RateLimitConfig.CHAT)))
            .thenReturn(new RateLimiter.RateLimitResult(true, 1, 123L));

        filter.doFilter(request, response, chain);

        ArgumentCaptor<String> keyCaptor = ArgumentCaptor.forClass(String.class);
        verify(rateLimiter).check(keyCaptor.capture(), eq(RateLimitConfig.CHAT));
        assertEquals("user:42", keyCaptor.getValue());
        verify(chain).doFilter(request, response);
    }

    @Test
    void fallsBackToRemoteAddressForAnonymousRequest() throws Exception {
        when(request.getRequestURI()).thenReturn("/api/trip/chat");
        when(request.getRemoteAddr()).thenReturn("203.0.113.9");
        when(rateLimiter.check(anyString(), eq(RateLimitConfig.CHAT)))
            .thenReturn(new RateLimiter.RateLimitResult(true, 1, 123L));

        filter.doFilter(request, response, chain);

        ArgumentCaptor<String> keyCaptor = ArgumentCaptor.forClass(String.class);
        verify(rateLimiter).check(keyCaptor.capture(), eq(RateLimitConfig.CHAT));
        assertEquals("ip:203.0.113.9", keyCaptor.getValue());
    }
}
