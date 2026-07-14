"""Admin controller (agent trace, MCP stats, etc.)"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.config.database import get_db
from src.middleware.auth import require_admin
from src.services.admin_service import AdminService
from src.models.user import User


router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/agent-trace/{message_id}", response_model=dict, summary="获取 Agent 执行轨迹")
async def get_agent_trace(
    message_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取单条消息的 Agent 执行轨迹
    
    Args:
        message_id: 消息ID
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含消息和步骤的响应
    """
    try:
        trace = await AdminService.get_agent_trace(db, message_id)
        return {
            "code": 200,
            "data": trace,
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/agent-trace", response_model=dict, summary="获取 Agent 执行轨迹摘要列表")
async def get_agent_trace_summary(
    conversation_id: int = Query(..., description="对话ID"),
    limit: int = Query(20, ge=1, le=100, description="返回条数"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取对话的 Agent 执行轨迹摘要列表
    
    Args:
        conversation_id: 对话ID
        limit: 返回条数（1-100）
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含摘要列表的响应
    """
    try:
        summaries = await AdminService.get_agent_trace_summary(db, conversation_id, limit)
        return {
            "code": 200,
            "data": {"summaries": summaries},
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/mcp-stats", response_model=dict, summary="获取 MCP 进程状态和调用指标")
async def get_mcp_stats(
    current_user: User = Depends(require_admin),
):
    """获取高德 MCP server 进程状态和调用指标。
    
    对标 Node 版 GET /api/admin/mcp-stats。
    
    Returns:
        dict: 包含进程存活状态和调用指标的响应
    """
    from src.services.mcp.amap_process import is_amap_mcp_alive
    from src.services.mcp.guards import mcp_metrics

    alive = await is_amap_mcp_alive()

    return {
        "code": 200,
        "data": {
            "alive": alive,
            "metrics": {
                "calls": mcp_metrics.calls,
                "successes": mcp_metrics.successes,
                "failures": mcp_metrics.failures,
                "cacheHits": mcp_metrics.cache_hits,
                "circuitOpenCount": mcp_metrics.circuit_open_count,
                "avgDurationMs": round(mcp_metrics.avg_duration_ms, 2),
            },
        },
        "message": "获取成功",
        "error": None,
    }
