"""PasswordReset model (password_resets table)"""

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.orm import relationship

from src.models.base import Base, BaseModelWithoutUpdatedAt


class PasswordReset(Base, BaseModelWithoutUpdatedAt):
    """PasswordReset model (no updated_at field)"""
    
    __tablename__ = "password_resets"
    __table_args__ = ({"comment": "密码重置表"},)
    
    # Fields (id and created_at inherited from BaseModelWithoutUpdatedAt)
    email = Column(
        String(100),
        nullable=False,
        comment="用户邮箱"
    )
    token = Column(
        String(255),
        unique=True,
        nullable=False,
        comment="重置令牌"
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="过期时间"
    )
    used = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否已使用"
    )
    
    def __repr__(self):
        return f"<PasswordReset(id={self.id}, email={self.email})>"
