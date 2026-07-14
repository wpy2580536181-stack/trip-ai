"""Conversation service (business logic)"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from src.models.conversation import Conversation
from src.models.message import Message
from src.schemas.conversation import ConversationCreate, ConversationResponse
from src.exceptions import NotFoundException
from src.utils.serialization import attach_count
from src.utils.tokens import estimate_tokens, get_history_max_tokens

logger = logging.getLogger(__name__)


async def load_context(
    db: AsyncSession,
    conversation_id: int,
) -> Dict[str, Any]:
    """加载对话上下文（供 Agent 使用）。

    从 Node.js loadContext() 迁移。
    - 过滤掉已压缩的消息（excluded_from_context=true）
    - 返回 system_summary + conversation_recap + 未压缩消息

    Args:
        db: 数据库会话。
        conversation_id: 对话 ID。

    Returns:
        Dict: {
            "system_summary": str | None,
            "conversation_recap": str | None,
            "recent_messages": List[Dict],
        }
    """
    # 1. 加载对话（含 summary/recap）
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()

    system_summary = conversation.summary if conversation else None
    conversation_recap = getattr(conversation, "recap", None)

    # 2. 加载未压缩消息（按时间正序），过滤 excluded_from_context
    msg_result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.excluded_from_context != True,  # noqa: E712
        )
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    # 过滤掉空 content 消息（占位消息）
    recent_messages: List[Dict[str, Any]] = []
    for msg in messages:
        if not msg.content:
            continue
        recent_messages.append({
            "role": msg.role,
            "content": msg.content,
        })

    return {
        "system_summary": system_summary,
        "conversation_recap": conversation_recap,
        "recent_messages": recent_messages,
    }


async def get_context_messages(
    db: AsyncSession,
    conversation_id: int,
    max_tokens: int,
) -> Dict[str, Any]:
    """获取对话上下文消息（单调追加模式，不 shift）。

    保持 prefix 稳定以命中 LLM prompt cache。
    - 返回所有未压缩的原始消息（按时间正序）
    - 返回 needs_compaction 标志告诉调用方“该压缩了”

    Args:
        db: 数据库会话
        conversation_id: 对话 ID
        max_tokens: 最大 token 数

    Returns:
        {"messages": list, "total_tokens": int, "needs_compaction": bool}
    """
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.excluded_from_context != True,  # noqa: E712
        )
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()

    # 过滤掉空 content 消息
    real_messages = [
        {"role": m.role, "content": m.content, "id": m.id}
        for m in messages
        if m.content
    ]

    total_tokens = sum(estimate_tokens(m["content"]) for m in real_messages)

    return {
        "messages": real_messages,
        "total_tokens": total_tokens,
        "needs_compaction": total_tokens > max_tokens,
    }


async def get_recent_messages(
    db: AsyncSession,
    conversation_id: int,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """获取最近 N 条消息（按时间正序）。

    Args:
        db: 数据库会话
        conversation_id: 对话 ID
        limit: 最多返回条数

    Returns:
        消息列表（按时间正序）
    """
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()

    return [
        {"role": m.role, "content": m.content, "id": m.id}
        for m in reversed(messages)
    ]


async def update_summary(
    db: AsyncSession,
    conversation_id: int,
    summary: str,
) -> None:
    """更新对话摘要（供 Agent 回调使用）。"""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        conversation.summary = summary
        conversation.summary_at = func.now()
        await db.commit()


async def auto_title(
    db: AsyncSession,
    conversation_id: int,
    first_user_message: str,
) -> None:
    """根据首条用户消息自动生成标题。"""
    title = first_user_message[:20] + ("..." if len(first_user_message) > 20 else "")
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        conversation.title = title
        await db.commit()


class ConversationService:
    """Conversation service (business logic)"""
    
    @staticmethod
    async def get_conversations(
        db: AsyncSession, 
        user_id: int, 
        page: int = 1, 
        page_size: int = 20
    ) -> tuple:
        """获取对话列表（分页，含 _count）
        
        Args:
            db: Database session
            user_id: User ID
            page: Page number (1-based)
            page_size: Page size
            
        Returns:
            tuple: (conversations, total)
        """
        # 1. Build base query
        query = select(Conversation).where(
            Conversation.user_id == user_id
        ).order_by(Conversation.updated_at.desc())
        
        # 2. Get total count
        count_query = select(func.count()).select_from(
            select(Conversation).where(Conversation.user_id == user_id).subquery()
        )
        total = await db.scalar(count_query)
        
        # 3. Get paginated results
        offset = (page - 1) * page_size
        result = await db.execute(
            query.offset(offset).limit(page_size)
        )
        conversations = result.scalars().all()
        
        # 4. Attach _count (message count) to each conversation using attach_count
        conversations_with_count = await attach_count(
            db,
            conversations,
            Message,
            fk_field="conversation_id",
            count_name="messages"
        )
        
        return conversations_with_count, total
    
    @staticmethod
    async def get_conversation(
        db: AsyncSession, 
        conversation_id: int, 
        user_id: int
    ) -> Conversation:
        """获取单个对话详情
        
        Args:
            db: Database session
            conversation_id: Conversation ID
            user_id: User ID (for authorization)
            
        Returns:
            Conversation: Conversation object with messages
            
        Raises:
            NotFoundException: if conversation not found or doesn't belong to user
        """
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id
            ).options(selectinload(Conversation.messages))
        )
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise NotFoundException("对话")
        
        return conversation
    
    @staticmethod
    async def create_conversation(
        db: AsyncSession, 
        user_id: int, 
        data: ConversationCreate
    ) -> Conversation:
        """创建新对话
        
        Args:
            db: Database session
            user_id: User ID
            data: Conversation creation data
            
        Returns:
            Conversation: Created conversation
        """
        conversation = Conversation(
            user_id=user_id,
            title=data.title,
            summary=None,
            summary_error=False,
            summary_at=None
        )
        
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        
        return conversation
    
    @staticmethod
    async def delete_conversation(
        db: AsyncSession, 
        conversation_id: int, 
        user_id: int
    ) -> bool:
        """删除对话
        
        Args:
            db: Database session
            conversation_id: Conversation ID
            user_id: User ID (for authorization)
            
        Returns:
            bool: True if successful
            
        Raises:
            NotFoundException: if conversation not found or doesn't belong to user
        """
        # 1. Find conversation
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id
            )
        )
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            raise NotFoundException("对话")
        
        # 2. Delete conversation (cascade will delete messages and agent_steps)
        await db.delete(conversation)
        await db.commit()
        
        return True
