package com.trip.backend.web.config;

import com.trip.backend.web.filter.*;
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
 * 5. CorsFilter（CORS，由 CorsConfig 提供）
 *
 * 注：IdempotencyFilter 和 ConcurrencyGuardFilter 后续在 B7 任务中添加
 */
@Configuration
public class FilterOrderConfig {

    @Bean
    public FilterRegistrationBean<RequestIdFilter> requestIdFilterRegistration(RequestIdFilter filter) {
        FilterRegistrationBean<RequestIdFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setOrder(1); // 最高优先级
        return registration;
    }

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

    // CorsFilter 由 CorsConfig 自动注册，order=0（Spring Security 默认）
}
