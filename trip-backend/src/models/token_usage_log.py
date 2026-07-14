"""TokenUsageLog model (token_usage_logs table)"""

from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Index, BigInteger
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModel


class TokenUsageLog(Base, BaseModel):
    """Token 使用记录模型。
    
    用于记录每次 Agent 请求的 Token 消耗。
    """
    
    __tablename__ = "token_usage_logs"
    __table_args__ = (
        Index("idx_token_logs_user_time", "user_id", "created_at"),
        Index("idx_token_logs_request_type", "request_type"),
        {"comment": "Token使用记录表"},
    )
    
    # Fields (id, created_at, updated_at inherited from BaseModel)
    user_id = Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="用户ID"
    )
    request_type = Column(
        "request_type",
        String(20),
        nullable=False,
        comment="请求类型（chat/recommend）"
    )
    route = Column(
        "route",
        String(50),
        nullable=True,
        comment="路由结果（planning/general）"
    )
    conversation_id = Column(
        "conversation_id",
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        comment="对话ID"
    )
    message_id = Column(
        "message_id",
        Integer,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="消息ID"
    )
    prompt_tokens = Column(
        "prompt_tokens",
        Integer,
        nullable=False,
        default=0,
        comment="输入 Token 数"
    )
    completion_tokens = Column(
        "completion_tokens",
        Integer,
        nullable=False,
        default=0,
        comment="输出 Token 数"
    )
    total_tokens = Column(
        "total_tokens",
        Integer,
        nullable=False,
        default=0,
        comment="总 Token 数"
    )
    cached_tokens = Column(
        "cached_tokens",
        Integer,
        nullable=False,
        default=0,
        comment="缓存 Token 数"
    )
    latency_ms = Column(
        "latency_ms",
        Integer,
        nullable=True,
        comment="延迟（毫秒）"
    )
    
    # Relationships
    user = relationship("User", back_populates="token_logs")
    conversation = relationship("Conversation", back_populates="token_logs")
    
    def __repr__(self):
        return f"<TokenUsageLog(id={self.id}, user_id={self.id}, total_tokens={self.total_tokens})>"
