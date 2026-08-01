package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.Map;

/**
 * 用户实体（对应 Python models/user.py）
 * - preferences 为 JSONB 列
 */
@Entity
@Table(name = "users")
@Getter
@Setter
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(nullable = false, unique = true, length = 100)
    private String email;

    @Column(nullable = false, length = 255)
    private String password; // bcrypt hash

    @Column(length = 50)
    private String nickname;

    @Column(length = 255)
    private String avatar;

    @Column(length = 20)
    private String phone;

    @Column(length = 255)
    private String bio;

    @Column(nullable = false)
    private Integer roleId = 2; // 默认普通用户

    @Column(nullable = false)
    private Integer status = 1; // 1=活跃，0=禁用

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> preferences;

    // 构造函数
    protected User() {}

    // Getters/Setters 由 Lombok 生成
}
