"""Spot model (spots table)"""

from sqlalchemy import Column, Integer, String, Float, JSON, Text, DateTime, Index
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from src.models.base import Base, BaseModel


class Spot(Base, BaseModel):
    """Spot model"""
    
    __tablename__ = "spots"
    __table_args__ = (
        Index("idx_spots_city_category", "city", "category"),
        Index(
            "idx_spots_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        {"comment": "景点表"},
    )
    
    # Fields
    name = Column(
        String(100),
        nullable=False,
        comment="景点名称"
    )
    city = Column(
        String(50),
        nullable=False,
        comment="城市"
    )
    category = Column(
        String(20),
        nullable=False,
        comment="分类"
    )
    description = Column(
        Text,
        nullable=False,
        comment="描述"
    )
    tags = Column(
        JSON,
        nullable=False,
        comment="标签（JSON数组）"
    )
    avg_cost = Column(
        "avg_cost",
        Float,
        nullable=True,
        comment="平均花费"
    )
    duration = Column(
        String(50),
        nullable=True,
        comment="推荐游览时长"
    )
    open_time = Column(
        "open_time",
        String(100),
        nullable=True,
        comment="开放时间"
    )
    rating = Column(
        Float,
        nullable=True,
        comment="评分"
    )
    embedding = Column(
        Vector(512),
        nullable=True,
        comment="景点描述向量（bge-small-zh-v1.5, 512维）"
    )
    
    def __repr__(self):
        return f"<Spot(id={self.id}, name={self.name}, city={self.city})>"
