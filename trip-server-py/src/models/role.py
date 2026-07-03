"""Role model (roles table)"""

from enum import Enum
from sqlalchemy import Column, String, Enum as SQLEnum
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModelWithoutUpdatedAt


class RoleName(str, Enum):
    """RoleName enum matching Prisma schema"""
    ADMIN = "ADMIN"
    USER = "USER"


class Role(Base, BaseModelWithoutUpdatedAt):
    """Role model (no updated_at field)"""
    
    __tablename__ = "roles"
    __table_args__ = ({"comment": "角色表"},)
    
    # Fields
    name = Column(
        SQLEnum(RoleName),
        unique=True,
        nullable=False,
        comment="角色名称"
    )
    
    # Relationships
    users = relationship("User", back_populates="role")
    
    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name})>"
