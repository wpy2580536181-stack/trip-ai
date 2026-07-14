"""Conversation model (conversations table)"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModel


class Conversation(Base, BaseModel):
    """Conversation model matching Prisma schema"""
    
    __tablename__ = "conversations"
    __table_args__ = (
        {"comment": "对话表"},
    )
    
    # Fields
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="用户ID（外键）"
    )
    title = Column(
        String(100),
        nullable=True,
        comment="对话标题"
    )
    summary = Column(
        Text,
        nullable=True,
        comment="对话摘要"
    )
    recap = Column(
        Text,
        nullable=True,
        comment="对话回顾"
    )
    summary_error = Column(
        Boolean,
        default=False,
        nullable=True,
        comment="摘要是否出错"
    )
    summary_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="摘要生成时间"
    )
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    token_logs = relationship(
        "TokenUsageLog",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, title={self.title})>"
