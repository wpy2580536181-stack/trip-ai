"""Stats service (business logic)"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, timedelta, timezone

from src.models.token_usage_log import TokenUsageLog


class StatsService:
    """Stats service class"""
    
    @staticmethod
    async def get_token_stats(
        db: AsyncSession,
        user_id: int,
        scope: str
    ) -> dict:
        """获取 Token 使用统计
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            scope: 统计范围（user/global）
            
        Returns:
            dict: 统计信息
        """
        # 计算时间窗口（过去 1 小时）
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        
        # 构建查询
        query = select(func.sum(TokenUsageLog.total_tokens)).where(
            TokenUsageLog.created_at >= one_hour_ago
        )
        
        if scope == "user":
            query = query.where(TokenUsageLog.user_id == user_id)
        
        # 执行查询
        result = await db.execute(query)
        current_usage = result.scalar() or 0
        
        # 获取限制（从配置中读取）
        from src.config.settings import settings
        if scope == "user":
            limit = settings.token_budget_user
        else:
            limit = settings.token_budget_global
        
        return {
            "window": {
                "current": current_usage,
                "limit": limit,
                "resetAt": int(one_hour_ago.timestamp() * 1000),  # 毫秒
            },
            "totalSinceStart": 0,  # TODO: 从数据库查询总使用量
        }
    
    @staticmethod
    async def get_token_logs(
        db: AsyncSession,
        user_id: int,
        scope: str,
        limit: int = 50
    ) -> dict:
        """获取 Token 使用日志
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            scope: 统计范围（user/global）
            limit: 返回条数
            
        Returns:
            dict: 日志列表
        """
        # 构建查询
        query = select(TokenUsageLog).order_by(TokenUsageLog.created_at.desc()).limit(limit)
        
        if scope == "user":
            query = query.where(TokenUsageLog.user_id == user_id)
        
        # 执行查询
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # 转换为字典列表
        log_list = [
            {
                "id": log.id,
                "userId": log.user_id,
                "requestType": log.request_type,
                "route": log.route,
                "conversationId": log.conversation_id,
                "messageId": log.message_id,
                "promptTokens": log.prompt_tokens,
                "completionTokens": log.completion_tokens,
                "totalTokens": log.total_tokens,
                "cachedTokens": log.cached_tokens,
                "latencyMs": log.latency_ms,
                "createdAt": int(log.created_at.timestamp() * 1000),  # 毫秒
            }
            for log in logs
        ]
        
        return {
            "logs": log_list
        }
