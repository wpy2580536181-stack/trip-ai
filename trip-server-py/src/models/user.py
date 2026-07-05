"""User model (users table)"""

from sqlalchemy import Column, String, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModel


class User(Base, BaseModel):
    """User model matching Prisma schema"""
    
    __tablename__ = "users"
    __table_args__ = ({"comment": "用户表"},)
    
    # Fields (matching Prisma schema exactly)
    username = Column(
        String(50),
        unique=True,
        nullable=False,
        comment="用户名"
    )
    email = Column(
        String(100),
        unique=True,
        nullable=False,
        comment="邮箱"
    )
    password = Column(
        String(255),
        nullable=False,
        comment="密码（bcrypt hash）"
    )
    nickname = Column(
        String(50),
        nullable=True,
        comment="昵称"
    )
    avatar = Column(
        String(255),
        nullable=True,
        comment="头像URL"
    )
    phone = Column(
        String(20),
        nullable=True,
        comment="手机号"
    )
    bio = Column(
        String(255),
        nullable=True,
        comment="个人简介"
    )
    role_id = Column(
        Integer,
        ForeignKey("roles.id"),
        default=2,
        nullable=False,
        comment="角色ID（外键）"
    )
    status = Column(
        Integer,
        default=1,
        nullable=False,
        comment="状态（1=活跃，0=禁用）"
    )
    preferences = Column(
        JSON,
        nullable=True,
        comment="用户偏好（JSON）"
    )
    
    # Relationships
    role = relationship("Role", back_populates="users")
    trips = relationship("Trip", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    feedbacks = relationship("Feedback", back_populates="user")
    token_logs = relationship("TokenUsageLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"
