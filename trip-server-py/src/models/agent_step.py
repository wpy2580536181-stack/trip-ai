"""AgentStep model (agent_steps table)"""

from sqlalchemy import Column, Integer, String, JSON, ForeignKey, Text, Index
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModelWithoutUpdatedAt


class AgentStep(Base, BaseModelWithoutUpdatedAt):
    """AgentStep model matching Prisma schema (no updated_at field)"""
    
    __tablename__ = "agent_steps"
    __table_args__ = (
        Index("idx_agent_steps_msg_step", "message_id", "step"),
        {"comment": "Agent步骤表"},
    )
    
    # Fields (id and created_at inherited from BaseModelWithoutUpdatedAt)
    message_id = Column(
        "message_id",
        Integer,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        comment="消息ID（外键）"
    )
    step = Column(
        Integer,
        nullable=False,
        comment="步骤序号"
    )
    type = Column(
        String(20),
        nullable=False,
        comment="步骤类型"
    )
    name = Column(
        String(100),
        nullable=True,
        comment="步骤名称"
    )
    args = Column(
        JSON,
        nullable=True,
        comment="参数（JSON）"
    )
    output = Column(
        Text,
        nullable=True,
        comment="输出"
    )
    duration_ms = Column(
        "duration_ms",
        Integer,
        nullable=True,
        comment="耗时（毫秒）"
    )
    error = Column(
        Text,
        nullable=True,
        comment="错误信息"
    )
    
    # Relationships
    message = relationship("Message", back_populates="steps")
    
    def __repr__(self):
        return f"<AgentStep(id={self.id}, step={self.step}, type={self.type})>"
