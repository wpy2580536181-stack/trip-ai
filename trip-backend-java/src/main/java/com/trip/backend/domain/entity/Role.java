package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

/**
 * 角色实体（对应 Python models/role.py）
 */
@Entity
@Table(name = "roles")
@Getter
@Setter
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
}
