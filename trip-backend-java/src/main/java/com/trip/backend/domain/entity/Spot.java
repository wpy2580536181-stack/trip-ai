package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;

/**
 * 景点实体（对应 Python models/spot.py）
 * - embedding 字段 @Transient（不映射到 JPA，走原生 SQL）
 * - tags 为 JSONB 列
 * - (city, category) 索引 + HNSW 向量索引（原生 SQL 创建）
 */
@Entity
@Table(name = "spots", indexes = {
    @Index(name = "idx_spots_city_category", columnList = "city, category"),
    @Index(name = "idx_spots_name", columnList = "name")
})
@Getter
@Setter
public class Spot {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, length = 100)
    private String city;

    @Column(nullable = false, length = 100)
    private String category;

    @Lob
    private String description;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> tags;

    @Column
    private Integer avgCost;

    @Column
    private Integer duration; // 建议游览时间（分钟）

    @Column(length = 100)
    private String openTime;

    @Column
    private Double rating;

    @Column
    private OffsetDateTime createdAt;

    // embedding 列不映射到 JPA（@Transient），走原生 SQL
    @Transient
    private Object embedding; // float[] 或 String（原始 SQL 结果）

    protected Spot() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }
}
