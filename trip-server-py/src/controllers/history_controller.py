"""History controller (HTTP handlers)"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.middleware.auth import get_current_user
from src.schemas.history import TripResponse
from src.services.history_service import HistoryService
from src.models.user import User

router = APIRouter(prefix="/api/trips", tags=["Trip History"])


@router.get(
    "",
    response_model=dict,
    summary="获取行程历史列表",
    description="""
    获取当前登录用户的行程历史列表（分页）。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    查询参数：
    - page: 页码（从1开始，默认1）
    - page_size: 每页数量（1-100，默认20）
    
    返回行程列表，按创建时间倒序排列。
    
    错误响应：
    - 401: 未授权或token已过期
    """
)
async def get_trips(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取行程历史列表
    
    Args:
        page: 页码（从1开始）
        page_size: 每页数量
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含行程列表和分页信息的响应
    """
    trips, total = await HistoryService.get_trips(
        db, current_user.id, page, page_size
    )
    
    # Convert to response format using Pydantic model (use alias names)
    items = [
        TripResponse(
            id=trip.id,
            userId=trip.user_id,
            fromCity=trip.from_city,
            city=trip.city,
            days=trip.days,
            budget=trip.budget,
            content=trip.content,
            status=trip.status,
            parentTripId=trip.parent_trip_id,
            createdAt=trip.created_at,
            updatedAt=None  # Trip model doesn't have updated_at
        )
        for trip in trips
    ]
    
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size
        },
        "message": "获取行程历史成功",
        "error": None
    }


@router.get(
    "/{trip_id}",
    response_model=dict,
    summary="获取行程详情",
    description="""
    获取指定行程的详细信息。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    路径参数：
    - trip_id: 行程ID
    
    返回行程详情，包含完整的content字段（AI生成的行程内容）。
    
    错误响应：
    - 401: 未授权或token已过期
    - 404: 行程不存在或无权限访问
    """
)
async def get_trip(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取行程详情
    
    Args:
        trip_id: 行程ID
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含行程详情的响应
        
    Raises:
        HTTPException: 404 如果行程不存在或无权限访问
    """
    trip = await HistoryService.get_trip(
        db, trip_id, current_user.id
    )
    
    return {
        "code": 200,
        "data": {
            "id": trip.id,
            "user_id": trip.user_id,
            "from_city": trip.from_city,
            "city": trip.city,
            "days": trip.days,
            "budget": trip.budget,
            "content": trip.content,
            "status": trip.status,
            "parent_trip_id": trip.parent_trip_id,
            "created_at": trip.created_at,
            "updated_at": None  # Trip model doesn't have updated_at
        },
        "message": "获取行程详情成功",
        "error": None
    }


@router.delete(
    "/{trip_id}",
    response_model=dict,
    summary="删除行程",
    description="""
    删除指定行程。
    
    需要在请求头中包含有效的JWT token：
    - Authorization: Bearer <token>
    
    路径参数：
    - trip_id: 行程ID
    
    错误响应：
    - 401: 未授权或token已过期
    - 404: 行程不存在或无权限删除
    """
)
async def delete_trip(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除行程
    
    Args:
        trip_id: 行程ID
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        dict: 包含成功消息的响应
        
    Raises:
        HTTPException: 404 如果行程不存在或无权限删除
    """
    await HistoryService.delete_trip(
        db, trip_id, current_user.id
    )
    
    return {
        "code": 200,
        "data": None,
        "message": "删除行程成功",
        "error": None
    }
