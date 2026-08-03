package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;
import java.util.Map;

/**
 * 行程实体（对应 Python models/trip.py）
 * - content 为 JSONB 列
 * - parent_trip_id 自引用（版本链）
 * - 无 updated_at
 */
@Entity
@Table(name = "trips", indexes = {
    @Index(name = "idx_trips_user_id", columnList = "user_id"),
    @Index(name = "idx_trips_status", columnList = "status"),
    @Index(name = "idx_trips_parent_trip_id", columnList = "parent_trip_id")
})
public class Trip {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long userId;

    @Column(length = 100)
    private String fromCity;

    @Column(nullable = false, length = 100)
    private String city;

    @Column(nullable = false)
    private Integer days;

    @Column(nullable = false)
    private Integer budget;

    // JSONB 列
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "json")
    private Map<String, Object> content;

    @Column(nullable = false, length = 50)
    private String status = "completed"; // candidate / completed / discarded

    // 版本链（自引用）
    @Column(name = "parent_trip_id")
    private Long parentTripId;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    // 无 updated_at

    public Trip() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public Long getUserId() {
        return userId;
    }

    public String getFromCity() {
        return fromCity;
    }

    public String getCity() {
        return city;
    }

    public Integer getDays() {
        return days;
    }

    public Integer getBudget() {
        return budget;
    }

    public Map<String, Object> getContent() {
        return content;
    }

    public String getStatus() {
        return status;
    }

    public Long getParentTripId() {
        return parentTripId;
    }

    public OffsetDateTime getCreatedAt() {
        return createdAt;
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public void setFromCity(String fromCity) {
        this.fromCity = fromCity;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public void setDays(Integer days) {
        this.days = days;
    }

    public void setBudget(Integer budget) {
        this.budget = budget;
    }

    public void setContent(Map<String, Object> content) {
        this.content = content;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public void setParentTripId(Long parentTripId) {
        this.parentTripId = parentTripId;
    }

    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }

    // ==================== Builder Factory (供 Service 层使用) ====================

    public static Trip create(Long userId, String city, Integer days, Integer budget) {
        Trip trip = new Trip();
        trip.setUserId(userId);
        trip.setCity(city);
        trip.setDays(days);
        trip.setBudget(budget);
        trip.setStatus("candidate");
        return trip;
    }
}
