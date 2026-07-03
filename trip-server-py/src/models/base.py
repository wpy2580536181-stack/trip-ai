"""SQLAlchemy Base and Mixins"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

# SQLAlchemy 2.0 declarative base
Base = declarative_base()


class BaseModel:
    """所有模型的基类，提供 id/created_at/updated_at
    
    使用方式：
    class MyModel(Base, BaseModel):
        __tablename__ = "my_table"
        # 自动获得 id, created_at, updated_at 字段
    """
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=None,
        server_default=None,
        onupdate=func.current_timestamp(),
        nullable=True,
        comment="更新时间"
    )


class BaseModelWithoutUpdatedAt:
    """无 updated_at 字段的模型基类
    
    用于：PasswordReset, Message, AgentStep 等只有 created_at 的表
    """
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键"
    )
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="创建时间"
    )
