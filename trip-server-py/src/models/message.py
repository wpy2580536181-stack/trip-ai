"""Message model (messages table)"""

from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModelWithoutUpdatedAt


class Message(Base, BaseModelWithoutUpdatedAt):
    """Message model matching Prisma schema (no updated_at field)"""
    
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_conv_created", "conversation_id", "created_at"),
        Index("idx_messages_conv_excluded", "conversation_id", "excluded_from_context"),
        {"comment": "消息表"},
    )
    
    # Fields (id and created_at inherited from BaseModelWithoutUpdatedAt)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        comment="对话ID（外键）"
    )
    role = Column(
        String(20),
        nullable=False,
        comment="角色（user/assistant/system/tool）"
    )
    content = Column(
        Text,
        nullable=False,
        comment="消息内容"
    )
    metadata_ = Column(
        "metadata",
        JSON,
        nullable=True,
        comment="元数据（JSON）"
    )
    excluded_from_context = Column(
        "excluded_from_context",
        Boolean,
        default=False,
        nullable=True,
        comment="是否已排除出上下文"
    )
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    feedbacks = relationship(
        "Feedback",
        back_populates="message",
        cascade="all, delete-orphan"
    )
    steps = relationship(
        "AgentStep",
        back_populates="message",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<Message(id={self.id}, role={self.role})>"
