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

    @Column(columnDefinition = "TEXT")
    private String description;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "json")
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

    // ==================== RerankWithCredibility 支持 ====================

    /**
     * 获取排序分数（用于 RerankWithCredibility）
     */
    public double getScore() {
        return rating != null ? rating : 0.0;
    }

    /**
     * 设置排序分数（Spot 实体暂不存储，使用 DTO 或 transient 字段）
     */
    public void setScore(double score) {
        // Spot 实体无 score 字段，暂不存储
    }

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCity() {
        return city;
    }

    public String getCategory() {
        return category;
    }

    public String getDescription() {
        return description;
    }

    public Map<String, Object> getTags() {
        return tags;
    }

    public Integer getAvgCost() {
        return avgCost;
    }

    public Integer getDuration() {
        return duration;
    }

    public String getOpenTime() {
        return openTime;
    }

    public Double getRating() {
        return rating;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    public String getAddress() {
        // TODO: 添加 address 字段到实体
        return null;
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setName(String name) {
        this.name = name;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public void setTags(Map<String, Object> tags) {
        this.tags = tags;
    }

    public void setAvgCost(Integer avgCost) {
        this.avgCost = avgCost;
    }

    public void setDuration(Integer duration) {
        this.duration = duration;
    }

    public void setOpenTime(String openTime) {
        this.openTime = openTime;
    }

    public void setRating(Double rating) {
        this.rating = rating;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public void setAddress(String address) {
        // TODO: 添加 address 字段到实体
    }

    // ==================== Builder Factory (供 Service 层使用) ====================

    /**
     * 创建新 Spot 实例（外部包无法访问 protected 构造器）
     */
    public static Spot create(String name, String city, String category) {
        Spot spot = new Spot();
        spot.setName(name);
        spot.setCity(city);
        spot.setCategory(category);
        return spot;
    }

    public boolean hasEmbedding() {
        return false;
    }
}
