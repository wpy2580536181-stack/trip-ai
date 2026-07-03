"""Spot model (spots table)"""

from sqlalchemy import Column, Integer, String, Float, JSON, Text, DateTime, Index
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModel


class Spot(Base, BaseModel):
    """Spot model matching Prisma schema"""
    
    __tablename__ = "spots"
    __table_args__ = (
        Index("idx_spots_city_category", "city", "category"),
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
    vector_id = Column(
        "vector_id",
        String(100),
        unique=True,
        nullable=True,
        comment="向量ID"
    )
    
    def __repr__(self):
        return f"<Spot(id={self.id}, name={self.name}, city={self.city})>"
