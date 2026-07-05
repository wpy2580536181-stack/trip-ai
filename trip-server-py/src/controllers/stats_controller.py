"""Stats controller (token usage stats)"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.config.database import get_db
from src.middleware.auth import get_current_user, require_admin
from src.services.stats_service import StatsService
from src.models.user import User


router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get("/token-usage/summary", response_model=dict, summary="获取 Token 使用统计摘要")
async def get_token_summary(
    scope: str = Query("user", description="统计范围（user/global）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取 Token 使用统计摘要
    
    Args:
        scope: 统计范围（user=当前用户，global=全局）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 包含统计摘要的响应
    """
    try:
        if scope == "global" and current_user.role_id != 1:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        
        stats = await StatsService.get_token_stats(db, current_user.id, scope)
        return {
            "code": 200,
            "data": stats,
            "message": "获取成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/token-usage/stats", response_model=dict, summary="获取 Token 使用统计")
async def get_token_stats(
    scope: str = Query("user", description="统计范围（user/global）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取 Token 使用统计
    
    Args:
        scope: 统计范围（user=当前用户，global=全局）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 包含统计信息的响应
    """
    try:
        if scope == "global" and current_user.role_id != 1:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        
        stats = await StatsService.get_token_stats(db, current_user.id, scope)
        return {
            "code": 200,
            "data": stats,
            "message": "获取成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/token-usage/logs", response_model=dict, summary="获取 Token 使用日志")
async def get_token_logs(
    scope: str = Query("user", description="统计范围（user/global）"),
    limit: int = Query(50, ge=1, le=100, description="返回条数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取 Token 使用日志
    
    Args:
        scope: 统计范围（user=当前用户，global=全局）
        limit: 返回条数（1-100）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 包含日志的响应
    """
    try:
        if scope == "global" and current_user.role_id != 1:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        
        logs = await StatsService.get_token_logs(db, current_user.id, scope, limit)
        return {
            "code": 200,
            "data": logs,
            "message": "获取成功",
            "error": None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
