"""Admin service (business logic)"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.models.agent_step import AgentStep
from src.models.message import Message


class AdminService:
    """Admin service class"""
    
    @staticmethod
    async def get_agent_trace(
        db: AsyncSession,
        message_id: int
    ) -> dict:
        """获取 Agent 执行轨迹
        
        Args:
            db: 数据库会话
            message_id: 消息ID
            
        Returns:
            dict: 消息和步骤信息
        """
        # 获取消息
        msg_stmt = select(Message).where(Message.id == message_id)
        msg_result = await db.execute(msg_stmt)
        message = msg_result.scalar_one_or_none()
        
        if not message:
            raise ValueError(f"消息不存在: {message_id}")
        
        # 获取步骤
        steps_stmt = select(AgentStep).where(
            AgentStep.message_id == message_id
        ).order_by(AgentStep.step)
        
        steps_result = await db.execute(steps_stmt)
        steps = steps_result.scalars().all()
        
        return {
            "message": {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "metadata": message.metadata,
                "createdAt": message.created_at.isoformat(),
                "conversationId": message.conversation_id,
                "_count": {"steps": len(steps)}
            },
            "steps": [
                {
                    "id": s.id,
                    "step": s.step,
                    "type": s.type,
                    "name": s.name,
                    "args": s.args,
                    "output": s.output,
                    "durationMs": s.duration_ms,
                    "error": s.error,
                    "createdAt": s.created_at.isoformat()
                }
                for s in steps
            ]
        }
    
    @staticmethod
    async def get_agent_trace_summary(
        db: AsyncSession,
        conversation_id: int,
        limit: int = 20
    ) -> list:
        """获取 Agent 执行轨迹摘要列表
        
        Args:
            db: 数据库会话
            conversation_id: 对话ID
            limit: 返回条数
            
        Returns:
            list: 摘要列表
        """
        # 获取对话的消息列表
        msg_stmt = select(Message).where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant"
        ).order_by(Message.id.desc()).limit(limit)
        
        msg_result = await db.execute(msg_stmt)
        messages = msg_result.scalars().all()
        
        summaries = []
        for msg in messages:
            # 获取步骤数
            steps_stmt = select(AgentStep).where(
                AgentStep.message_id == msg.id
            )
            steps_result = await db.execute(steps_stmt)
            steps = steps_result.scalars().all()
            
            # 提取 usage 信息
            usage = None
            if msg.metadata and isinstance(msg.metadata, dict):
                usage = msg.metadata.get("usage")
            
            summaries.append({
                "messageId": msg.id,
                "preview": msg.content[:100] if msg.content else "",
                "stepCount": len(steps),
                "usage": usage,
                "createdAt": msg.created_at.isoformat()
            })
        
        return summaries
