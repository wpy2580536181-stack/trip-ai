package com.trip.backend.web.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

import java.util.List;

/**
 * CORS 配置（对应 Python CORS 中间件）
 * - allow_origins 白名单
 * - headers 包含 X-Stream-Id/Last-Event-ID/x-request-id（SSE 断点续传）
 */
@Configuration
public class CorsConfig {

    @Bean
    public CorsFilter corsFilter() {
        CorsConfiguration config = new CorsConfiguration();

        // 允许的来源
        config.setAllowedOrigins(List.of(
            "http://localhost:5173",  // Vue dev server
            "http://localhost:3000"   // 备用端口
        ));

        // 允许的 HTTP 方法
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"));

        // 允许的 Headers（包含 SSE 断点续传专用头）
        config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-Id",
            "X-Stream-Id",
            "Last-Event-ID",
            "X-Idempotency-Key"
        ));

        // 暴露的 Headers
        config.setExposedHeaders(List.of(
            "X-Request-Id",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset"
        ));

        // 允许携带凭证
        config.setAllowCredentials(true);

        // 最大缓存时间（秒）
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);

        return new CorsFilter(source);
    }
}
