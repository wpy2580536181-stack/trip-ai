"""Conversation schemas (request/response)"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any


class ConversationCreate(BaseModel):
    """创建对话请求"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    title: str = Field(..., max_length=255, description="对话标题")
    model: str = Field(default="deepseek-chat", max_length=100, description="模型名称")


class ConversationResponse(BaseModel):
    """对话响应"""
    model_config = ConfigDict(
        serialize_by_alias=True,
        from_attributes=True
    )
    
    id: int
    user_id: int = Field(alias="userId")
    title: str
    summary: Optional[str] = None
    summary_error: Optional[bool] = Field(default=None, alias="summaryError")
    summary_at: Optional[datetime] = Field(default=None, alias="summaryAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")
    count: Optional[Dict[str, int]] = Field(default=None, alias="_count")


class ConversationListResponse(BaseModel):
    """对话列表响应（含 _count）"""
    model_config = ConfigDict(serialize_by_alias=True)
    
    items: List[ConversationResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
