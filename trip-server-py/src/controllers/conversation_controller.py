"""Conversation controller (HTTP handlers)"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.schemas.conversation import ConversationCreate, ConversationResponse, ConversationListResponse
from src.services.conversation_service import ConversationService
from src.models.user import User

router = APIRouter(prefix="/conversations", tags=["Conversation"])


@router.get(
    "",
    response_model=dict,
    summary="获取对话列表",
    description="""
    获取当前登录用户的对话列表（分页）。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    查询参数：
    - page: 页码（从1开始，默认1）
    - page_size: 每页数量（1-100，默认20）
    
    返回对话列表，每个对话包含消息数量（_count）。
    
    错误响应：
    - 401: 未授权或token已过期
    """
)
async def get_conversations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取对话列表
    
    Args:
        page: 页码（从1开始）
        page_size: 每页数量
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含对话列表和分页信息的响应
    """
    conversations, total = await ConversationService.get_conversations(
        db, current_user.id, page, page_size
    )
    
    # Use Pydantic model for automatic camelCase serialization
    items = [
        ConversationResponse(
            id=conv["id"],
            userId=conv["user_id"],
            title=conv["title"],
            summary=conv.get("summary"),
            summaryError=conv.get("summary_error"),
            summaryAt=conv.get("summary_at"),
            createdAt=conv["created_at"],
            updatedAt=conv.get("updated_at"),
            _count=conv.get("_count")
        )
        for conv in conversations
    ]
    
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size
        },
        "message": "获取对话列表成功",
        "error": None
    }


@router.get(
    "/{conversation_id}",
    response_model=dict,
    summary="获取对话详情",
    description="""
    获取指定对话的详细信息，包含消息列表。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    路径参数：
    - conversation_id: 对话ID
    
    返回对话详情和消息列表。
    
    错误响应：
    - 401: 未授权或token已过期
    - 404: 对话不存在或无权限访问
    """
)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取对话详情
    
    Args:
        conversation_id: 对话ID
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含对话详情和消息列表的响应
        
    Raises:
        HTTPException: 404 如果对话不存在或无权限访问
    """
    conversation = await ConversationService.get_conversation(
        db, conversation_id, current_user.id
    )
    
    # Convert to dict and let Pydantic handle serialization
    conversation_dict = {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "summary": conversation.summary,
        "summary_error": conversation.summary_error,
        "summary_at": conversation.summary_at,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            }
            for msg in conversation.messages
        ]
    }
    
    return {
        "code": 200,
        "data": conversation_dict,
        "message": "获取对话详情成功",
        "error": None
    }


@router.post(
    "",
    response_model=dict,
    status_code=201,
    summary="创建对话",
    description="""
    创建新对话。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    请求体必须包含：
    - title: 对话标题
    - model: 模型名称（可选，默认deepseek-chat）
    
    返回创建的对话信息。
    
    错误响应：
    - 401: 未授权或token已过期
    - 422: 请求参数验证失败
    """
)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建对话
    
    Args:
        data: 对话创建数据
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含创建对话信息的响应
    """
    conversation = await ConversationService.create_conversation(
        db, current_user.id, data
    )
    
    # Use Pydantic model for response (use alias names for camelCase)
    conversation_response = ConversationResponse(
        id=conversation.id,
        userId=conversation.user_id,
        title=conversation.title,
        summary=conversation.summary,
        summaryError=conversation.summary_error,
        summaryAt=conversation.summary_at,
        createdAt=conversation.created_at,
        updatedAt=conversation.updated_at
    )
    
    return {
        "code": 200,
        "data": conversation_response,
        "message": "创建对话成功",
        "error": None
    }


@router.delete(
    "/{conversation_id}",
    response_model=dict,
    summary="删除对话",
    description="""
    删除指定对话（级联删除消息和Agent步骤）。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    路径参数：
    - conversation_id: 对话ID
    
    错误响应：
    - 401: 未授权或token已过期
    - 404: 对话不存在或无权限删除
    """
)
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除对话
    
    Args:
        conversation_id: 对话ID
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含成功消息的响应
        
    Raises:
        HTTPException: 404 如果对话不存在或无权限删除
    """
    await ConversationService.delete_conversation(
        db, conversation_id, current_user.id
    )
    
    return {
        "code": 200,
        "data": None,
        "message": "删除对话成功",
        "error": None
    }
