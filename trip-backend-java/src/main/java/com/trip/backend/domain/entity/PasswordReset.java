package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

import java.time.OffsetDateTime;

/**
 * 密码重置实体（对应 Python models/password_reset.py）
 * - 表结构：email, token(unique), expires_at, used, created_at
 */
@Entity
@Table(name = "password_resets", indexes = {
    @Index(name = "idx_password_resets_token", columnList = "token", unique = true),
    @Index(name = "idx_password_resets_email", columnList = "email")
})
@Getter
@Setter
public class PasswordReset {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(nullable = false, length = 100)
    private String email;

    @Column(nullable = false, unique = true, length = 255)
    private String token;

    @Column(nullable = false)
    private OffsetDateTime expiresAt;

    @Column(nullable = false)
    private Boolean used = false;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    protected PasswordReset() {}

    public PasswordReset(String email, String token, OffsetDateTime expiresAt) {
        this.email = email;
        this.token = token;
        this.expiresAt = expiresAt;
        this.createdAt = OffsetDateTime.now();
        this.used = false;
    }

    /**
     * 检查令牌是否有效（未过期且未使用）
     */
    public boolean isValid() {
        return !used && expiresAt.isAfter(OffsetDateTime.now());
    }
}
