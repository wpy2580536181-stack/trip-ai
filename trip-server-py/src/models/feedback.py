"""Feedback model (feedbacks table)"""

from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModel


class Feedback(Base, BaseModel):
    """Feedback model matching Prisma schema"""
    
    __tablename__ = "feedbacks"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_feedback_user_message"),
        Index("idx_feedback_message", "message_id"),
        Index("idx_feedback_rating_created", "rating", "created_at"),
        Index("idx_feedback_user_created", "user_id", "created_at"),
        {"comment": "反馈表"},
    )
    
    # Fields
    user_id = Column(
        "user_id",
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        comment="用户ID（外键）"
    )
    message_id = Column(
        "message_id",
        Integer,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        comment="消息ID（外键）"
    )
    conversation_id = Column(
        "conversation_id",
        Integer,
        nullable=False,
        comment="对话ID"
    )
    rating = Column(
        Integer,
        nullable=False,
        comment="评分（1=点赞，-1=点踩）"
    )
    comment = Column(
        String(500),
        nullable=True,
        comment="评论"
    )
    tags = Column(
        JSON,
        nullable=True,
        comment="标签（JSON数组）"
    )
    
    # Relationships
    user = relationship("User", back_populates="feedbacks")
    message = relationship("Message", back_populates="feedbacks")
    
    def __repr__(self):
        return f"<Feedback(id={self.id}, rating={self.rating})>"
