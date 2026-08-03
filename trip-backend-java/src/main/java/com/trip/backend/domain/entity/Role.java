package com.trip.backend.domain.entity;

import jakarta.persistence.*;

/**
 * 角色实体（对应 Python models/role.py）
 */
@Entity
@Table(name = "roles")
public class Role {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Integer id;

    @Column(nullable = false, unique = true, length = 50)
    private String name; // ADMIN / USER

    // 构造函数
    protected Role() {}

    public Role(String name) {
        this.name = name;
    }

    // ==================== Getters ====================

    public Integer getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    // ==================== Setters ====================

    public void setId(Integer id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }
}
