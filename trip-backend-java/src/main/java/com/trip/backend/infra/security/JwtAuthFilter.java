package com.trip.backend.infra.security;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.crypto.SecretKey;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * JWT 认证 Filter（对应 Python auth.py）
 * - 缺 Authorization 头 → 403 "Not authenticated"
 * - 坏或过期 token → 401
 * - 仅强校验 userId 与 exp，授权以 DB role_id 为准（不信任 JWT 内 roleId）
 * - 设置 request attribute: userId, roleId（供 @RequestAttribute 使用）
 */
@Component
public class JwtAuthFilter extends OncePerRequestFilter {

    private final SecretKey key;

    public JwtAuthFilter(@Value("${jwt.secret}") String secret) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");

        // 1. 缺 Authorization 头 → 403
        if (header == null || header.isBlank()) {
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Not authenticated");
            return;
        }

        // 2. 提取 token（Bearer {token}）
        if (!header.startsWith("Bearer ")) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Invalid authorization header");
            return;
        }

        String token = header.substring(7);

        try {
            // 3. 解析 token
            Claims claims = Jwts.parser()
                .verifyWith(key)
                .build()
                .parseSignedClaims(token)
                .getPayload();

            // 4. 验证 userId 存在
            Object userIdObj = claims.get("userId");
            if (userIdObj == null) {
                response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Invalid token: missing userId");
                return;
            }

            // 5. 提取 userId 和 roleId
            Long userId = ((Number) userIdObj).longValue();
            Object roleIdObj = claims.get("roleId");
            Integer roleId = roleIdObj != null ? ((Number) roleIdObj).intValue() : null;

            // 6. 设置 request attribute（供 @RequestAttribute 使用）
            request.setAttribute("userId", userId);
            request.setAttribute("roleId", roleId);

            // 7. 构建 Authentication（仅包含 userId，role 从 DB 查询）
            var auth = new UsernamePasswordAuthenticationToken(
                userId,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );
            SecurityContextHolder.getContext().setAuthentication(auth);

            filterChain.doFilter(request, response);

        } catch (io.jsonwebtoken.ExpiredJwtException e) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Token expired");
        } catch (io.jsonwebtoken.JwtException e) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Invalid token");
        }
    }
}
