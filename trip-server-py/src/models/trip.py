"""Trip model (trips table)"""

from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModelWithoutUpdatedAt


class Trip(Base, BaseModelWithoutUpdatedAt):
    """Trip model matching Prisma schema (no updated_at field)"""
    
    __tablename__ = "trips"
    __table_args__ = (
        {"comment": "行程表"},
    )
    
    # Fields
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True,
        comment="用户ID（外键，可为空）"
    )
    from_city = Column(
        String(50),
        nullable=True,
        comment="出发城市"
    )
    city = Column(
        String(50),
        nullable=False,
        comment="目的地城市"
    )
    days = Column(
        Integer,
        nullable=False,
        comment="行程天数"
    )
    budget = Column(
        Integer,
        nullable=False,
        comment="预算"
    )
    content = Column(
        JSON,
        nullable=False,
        comment="行程内容（JSON）"
    )
    status = Column(
        String(20),
        default="completed",
        nullable=False,
        comment="状态"
    )
    parent_trip_id = Column(
        Integer,
        ForeignKey("trips.id"),
        nullable=True,
        comment="父行程ID（自引用）"
    )
    
    # Relationships
    user = relationship("User", back_populates="trips")
    parent = relationship(
        "Trip",
        remote_side="Trip.id",
        back_populates="versions",
        foreign_keys=[parent_trip_id]
    )
    versions = relationship(
        "Trip",
        back_populates="parent",
        foreign_keys=[parent_trip_id]
    )
    
    def __repr__(self):
        return f"<Trip(id={self.id}, city={self.city}, days={self.days})>"
