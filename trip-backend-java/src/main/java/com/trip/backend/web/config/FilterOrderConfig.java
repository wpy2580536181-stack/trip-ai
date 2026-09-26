package com.trip.backend.web.config;

import com.trip.backend.web.filter.*;
import com.trip.backend.middleware.ConcurrencyGuard;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.filter.CorsFilter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Filter 顺序配置（对应 Python 中间件链顺序）
 *
 * 执行顺序（从外到内）：
 * 1. RequestIdFilter（x-request-id）
 * 2. PrometheusFilter（指标收集）
 * 3. GzipFilter（GZip 压缩，SSE 跳过）
 * 4. GlobalRateLimitFilter（限流）
 * 5. IdempotencyFilter（幂等，仅 POST /api/trip/recommend）
 * 6. CorsFilter（CORS，由 CorsConfig 提供）
 *
 * 注：ConcurrencyGuardFilter 后续任务中添加
 */
@Configuration
public class FilterOrderConfig {

    @Bean
    public FilterRegistrationBean<RequestIdFilter> requestIdFilterRegistration(RequestIdFilter filter) {
        FilterRegistrationBean<RequestIdFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(1); // 最高优先级
        return registration;
    }

    // PrometheusFilter（指标收集）：RequestIdFilter 之后、GzipFilter 之前
    @Bean
    public FilterRegistrationBean<PrometheusFilter> prometheusFilterRegistration(PrometheusFilter filter) {
        FilterRegistrationBean<PrometheusFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(2);
        return registration;
    }

    @Bean
    public FilterRegistrationBean<GzipFilter> gzipFilterRegistration(GzipFilter filter) {
        FilterRegistrationBean<GzipFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(3);
        return registration;
    }

    @Bean
    public FilterRegistrationBean<GlobalRateLimitFilter> globalRateLimitFilterRegistration(GlobalRateLimitFilter filter) {
        FilterRegistrationBean<GlobalRateLimitFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(4);
        return registration;
    }

    // IdempotencyFilter（幂等）：限流之后（仅 POST /api/trip/recommend）
    @Bean
    public FilterRegistrationBean<IdempotencyFilter> idempotencyFilterRegistration(IdempotencyFilter filter) {
        FilterRegistrationBean<IdempotencyFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(5);
        return registration;
    }

    // CorsFilter：必须在所有业务 filter（JWT/限流）之前，否则 OPTIONS preflight 被拦成 401
    @Bean
    public FilterRegistrationBean<CorsFilter> corsFilterRegistration(CorsFilter filter) {
        FilterRegistrationBean<CorsFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(0); // 最外层，最先执行
        return registration;
    }

    @Bean
    public ConcurrencyGuard concurrencyGuard(
            @Value("${concurrency.global.limit:10}") int globalLimit,
            @Value("${concurrency.per-user.limit:1}") int perUserLimit) {
        return new ConcurrencyGuard(globalLimit, perUserLimit);
    }

    @Bean
    public FilterRegistrationBean<ConcurrencyGuardFilter> concurrencyGuardFilterRegistration(ConcurrencyGuardFilter filter) {
        FilterRegistrationBean<ConcurrencyGuardFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(6); // JWT/限流之后、controller 之前
        return registration;
    }
}
