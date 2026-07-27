"""SpotDoc model (spot_docs table) — RAG 文本层.

独立的真实语料层：维基百科 / Wikidata / 官方 POI 详情 / 合规 UGC 等外部
文本分块后入库，与事实层 spots 通过 spot_id 关联。每条文本带 5 维可信度
元信息（authority / freshness / agreement / citation / evidence），用于
检索融合与重排阶段的可信度加权。

设计原则（见 docs/rag-data-sources-and-credibility.md §6.3）：
- 事实层 Spot 表结构不动，文本层独立成表，避免混合后无法追溯血缘。
- 向量维度与 spots 一致（bge-small-zh-v1.5，512 维）。
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Index, ForeignKey,
)
from pgvector.sqlalchemy import Vector

from src.models.base import Base, BaseModel


class SpotDoc(Base, BaseModel):
    """文本层文档块（带可信度元信息）."""

    __tablename__ = "spot_docs"

    # 关联事实层景点（spots.id 为 Integer）
    spot_id = Column(
        Integer,
        ForeignKey("spots.id"),
        nullable=False,
        index=True,
        comment="关联景点 ID",
    )

    # 来源血缘
    source_type = Column(
        String(20),
        nullable=False,
        comment="来源类型: wiki/wikidata/official_gov/official_scenic/gaode_detail/osm/geonames/academic/ugc_authorized/ugc_public/llm_generated/realtime_mcp",
    )
    source_name = Column(
        String(50),
        comment="来源名称: 维基百科 / 高德 POI 详情",
    )
    source_url = Column(
        String(512),
        comment="原文链接（可追溯）",
    )
    title = Column(
        String(200),
        comment="文本块标题（如维基二级标题）",
    )
    content = Column(
        Text,
        nullable=False,
        comment="分块后的真实文本内容",
    )
    chunk_index = Column(
        Integer,
        default=0,
        comment="同 spot 内的分块序号",
    )

    # pgvector 向量列（bge-small-zh-v1.5, 512 维）
    embedding = Column(
        Vector(512),
        nullable=True,
        comment="文本块向量（bge-small-zh-v1.5, 512维）",
    )

    # ---- 5 维可信度元信息（写入时算好，检索时直接读取）----
    authority_score = Column(Float, default=0.5, comment="来源权威度 0~1")
    freshness_score = Column(Float, default=0.5, comment="信息新鲜度 0~1")
    agreement_score = Column(Float, default=0.0, comment="多源一致度 0~1")
    citation_count = Column(Integer, default=0, comment="引用/反向链接数")
    evidence_density = Column(Float, default=0.0, comment="证据密度 0~1")
    credibility_score = Column(Float, default=0.5, comment="综合可信度 0~1")

    # 时间元信息
    published_at = Column(DateTime(timezone=True), comment="原文发布时间")
    retrieved_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        comment="抓取时间",
    )

    __table_args__ = (
        Index("ix_spot_docs_source_type", "source_type"),
        Index(
            "idx_spot_docs_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"comment": "RAG 文本层文档块表（多源异构 + 可信度）"},
    )

    def __repr__(self):
        return f"<SpotDoc(id={self.id}, spot_id={self.spot_id}, source_type={self.source_type})>"
