package com.trip.backend.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Spring Security 配置
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthFilter jwtAuthFilter;

    public SecurityConfig(JwtAuthFilter jwtAuthFilter) {
        this.jwtAuthFilter = jwtAuthFilter;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                // 公开端点
                .requestMatchers(
                    "/api/user/register",
                    "/api/user/login",
                    "/api/user/forgot-password",
                    "/api/user/reset-password",
                    "/api/commute/**",
                    "/api/feedback/message/**",
                    "/api/feedback/list/**",
                    "/health",
                    "/health/**",
                    "/metrics",
                    "/actuator/**"
                ).permitAll()
                // Admin 端点
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                // 知识库公开端点
                .requestMatchers("/api/knowledge/spots", "/api/knowledge/spots/**", "/api/knowledge/spot-docs").permitAll()
                // 其他所有 /api/** 需要认证
                .requestMatchers("/api/**").authenticated()
                // 其他所有请求
                .anyRequest().permitAll()
            );

        // 添加 JWT Filter（在 UsernamePasswordAuthenticationFilter 之前）
        http.addFilterBefore(jwtAuthFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12);
    }
}
