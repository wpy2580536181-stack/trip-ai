package com.trip.backend.domain.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.OffsetDateTime;

/**
 * 景点文档实体（对应 Python models/spot_doc.py）
 * - embedding 字段 @Transient（不映射到 JPA，走原生 SQL）
 * - credibility 系列字段（authority/freshness/agreement/citation_count/evidence_density/credibility_score）
 */
@Entity
@Table(name = "spot_docs", indexes = {
    @Index(name = "idx_spot_docs_spot_id", columnList = "spot_id"),
    @Index(name = "idx_spot_docs_source_type", columnList = "source_type"),
    @Index(name = "idx_spot_docs_published_at", columnList = "published_at")
})
@Getter
@Setter
public class SpotDoc {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Long spotId;

    @Column(nullable = false, length = 50)
    private String sourceType; // wiki / poi / review / etc.

    @Column(length = 200)
    private String sourceName;

    @Column(length = 500)
    private String sourceUrl;

    @Column(nullable = false, length = 500)
    private String title;

    @Lob
    @Column(nullable = false)
    private String content;

    @Column(nullable = false)
    private Integer chunkIndex;

    // embedding 列不映射到 JPA（@Transient），走原生 SQL
    @Transient
    private Object embedding; // float[] 或 String（原始 SQL 结果）

    // 可信度字段
    @Column
    private Double authorityScore;

    @Column
    private Double freshnessScore;

    @Column
    private Double agreementScore;

    @Column
    private Integer citationCount;

    @Column
    private Double evidenceDensity;

    @Column
    private Double credibilityScore;

    @Column
    private OffsetDateTime publishedAt;

    @Column(nullable = false)
    private OffsetDateTime retrievedAt;

    protected SpotDoc() {}

    @PrePersist
    protected void onCreate() {
        this.retrievedAt = OffsetDateTime.now();
    }
}
