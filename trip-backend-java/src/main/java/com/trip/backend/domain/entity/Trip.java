package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
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
@Getter
@Setter
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
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> content;

    @Column(nullable = false, length = 50)
    private String status = "completed"; // candidate / completed / discarded

    // 版本链（自引用）
    @Column(name = "parent_trip_id")
    private Long parentTripId;

    @Column(nullable = false)
    private OffsetDateTime createdAt;

    // 无 updated_at

    protected Trip() {}

    @PrePersist
    protected void onCreate() {
        this.createdAt = OffsetDateTime.now();
    }
}
