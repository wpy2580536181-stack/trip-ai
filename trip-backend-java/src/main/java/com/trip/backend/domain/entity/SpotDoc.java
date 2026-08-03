package com.trip.backend.domain.entity;

import jakarta.persistence.*;
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

    // ==================== Getters ====================

    public Long getId() {
        return id;
    }

    public Long getSpotId() {
        return spotId;
    }

    public String getSourceType() {
        return sourceType;
    }

    public String getSourceName() {
        return sourceName;
    }

    public String getSourceUrl() {
        return sourceUrl;
    }

    public String getTitle() {
        return title;
    }

    public String getContent() {
        return content;
    }

    public Integer getChunkIndex() {
        return chunkIndex;
    }

    public Object getEmbedding() {
        return embedding;
    }

    public Double getAuthorityScore() {
        return authorityScore;
    }

    public Double getFreshnessScore() {
        return freshnessScore;
    }

    public Double getAgreementScore() {
        return agreementScore;
    }

    public Integer getCitationCount() {
        return citationCount;
    }

    public Double getEvidenceDensity() {
        return evidenceDensity;
    }

    public Double getCredibilityScore() {
        return credibilityScore;
    }

    public OffsetDateTime getPublishedAt() {
        return publishedAt;
    }

    public OffsetDateTime getRetrievedAt() {
        return retrievedAt;
    }

    // ==================== RerankWithCredibility 支持 ====================

    /**
     * 获取排序分数
     */
    public double getScore() {
        return credibilityScore != null ? credibilityScore : 0.0;
    }

    /**
     * 设置排序分数
     */
    public void setScore(double score) {
        // SpotDoc 暂不存储动态 score，如需存储可添加 transient 字段
    }

    // ==================== Setters ====================

    public void setId(Long id) {
        this.id = id;
    }

    public void setSpotId(Long spotId) {
        this.spotId = spotId;
    }

    public void setSourceType(String sourceType) {
        this.sourceType = sourceType;
    }

    public void setSourceName(String sourceName) {
        this.sourceName = sourceName;
    }

    public void setSourceUrl(String sourceUrl) {
        this.sourceUrl = sourceUrl;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public void setChunkIndex(Integer chunkIndex) {
        this.chunkIndex = chunkIndex;
    }

    public void setEmbedding(Object embedding) {
        this.embedding = embedding;
    }

    public void setAuthorityScore(Double authorityScore) {
        this.authorityScore = authorityScore;
    }

    public void setFreshnessScore(Double freshnessScore) {
        this.freshnessScore = freshnessScore;
    }

    public void setAgreementScore(Double agreementScore) {
        this.agreementScore = agreementScore;
    }

    public void setCitationCount(Integer citationCount) {
        this.citationCount = citationCount;
    }

    public void setEvidenceDensity(Double evidenceDensity) {
        this.evidenceDensity = evidenceDensity;
    }

    public void setCredibilityScore(Double credibilityScore) {
        this.credibilityScore = credibilityScore;
    }

    public void setPublishedAt(OffsetDateTime publishedAt) {
        this.publishedAt = publishedAt;
    }

    public void setRetrievedAt(OffsetDateTime retrievedAt) {
        this.retrievedAt = retrievedAt;
    }
}
