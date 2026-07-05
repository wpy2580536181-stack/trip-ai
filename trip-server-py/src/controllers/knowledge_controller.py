"""Knowledge controller (HTTP handlers)"""

from fastapi import APIRouter, Depends, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any

from src.config.database import get_db
from src.middleware.auth import get_current_user, require_admin
from src.middleware.rate_limiter import knowledge_rate_limiter
from src.schemas.knowledge import SpotCreate, SpotUpdate, SpotResponse, SpotListResponse
from src.services.knowledge_service import KnowledgeService
from src.models.user import User

router = APIRouter(
    prefix="/knowledge",
    tags=["Knowledge Base"],
    dependencies=[Depends(knowledge_rate_limiter)],
)


@router.get(
    "/spots",
    response_model=dict,
    summary="获取景点列表",
    description="""
    获取景点列表（公开接口，无需认证）。
    
    查询参数：
    - city: 按城市筛选（可选）
    - category: 按分类筛选（可选）
    - page: 页码（从1开始，默认1）
    - page_size: 每页数量（1-100，默认20）
    
    返回景点列表。
    
    错误响应：
    - 422: 请求参数验证失败
    """
)
async def get_spots(
    city: Optional[str] = Query(None, description="城市筛选"),
    category: Optional[str] = Query(None, description="分类筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页数量"),
    db: AsyncSession = Depends(get_db)
):
    """获取景点列表（公开）
    
    Args:
        city: 按城市筛选（可选）
        category: 按分类筛选（可选）
        page: 页码（从1开始）
        page_size: 每页数量
        db: 数据库会话
        
    Returns:
        dict: 包含景点列表和分页信息的响应
    """
    spots, total = await KnowledgeService.get_spots(
        db, city, category, page, page_size
    )
    
    # Convert to response format using Pydantic model
    items = [SpotResponse.model_validate(spot) for spot in spots]
    
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size
        },
        "message": "获取景点列表成功",
        "error": None
    }


@router.get(
    "/spots/{spot_id}",
    response_model=dict,
    summary="获取景点详情",
    description="""
    获取指定景点的详细信息（公开接口，无需认证）。
    
    路径参数：
    - spot_id: 景点ID
    
    返回景点详细信息。
    
    错误响应：
    - 404: 景点不存在
    """
)
async def get_spot(
    spot_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取景点详情（公开）
    
    Args:
        spot_id: 景点ID
        db: 数据库会话
        
    Returns:
        dict: 包含景点详情的响应
        
    Raises:
        HTTPException: 404 如果景点不存在
    """
    spot = await KnowledgeService.get_spot(db, spot_id)
    
    return {
        "code": 200,
        "data": {
            "id": spot.id,
            "name": spot.name,
            "city": spot.city,
            "category": spot.category,
            "description": spot.description,
            "tags": spot.tags,
            "avg_cost": spot.avg_cost,
            "duration": spot.duration,
            "open_time": spot.open_time,
            "rating": spot.rating,
            "vector_id": spot.vector_id,
            "created_at": spot.created_at.isoformat() if spot.created_at else None,
            "updated_at": spot.updated_at.isoformat() if spot.updated_at else None
        },
        "message": "获取景点详情成功",
        "error": None
    }


@router.post(
    "/spots",
    response_model=dict,
    summary="创建景点",
    description="""
    创建新景点（仅管理员）。
    
    需要在请求头中包含有效的JWT token（管理员权限）：
    - Authorization: Bearer <token>
    
    请求体必须包含：
    - name: 景点名称
    - city: 城市
    - category: 分类
    - description: 描述
    
    可选字段：
    - tags: 标签列表
    - avg_cost: 平均花费
    - duration: 推荐游览时长
    - open_time: 开放时间
    - rating: 评分
    
    错误响应：
    - 401: 未授权
    - 403: 权限不足（需要管理员权限）
    - 422: 请求参数验证失败
    """
)
async def create_spot(
    data: SpotCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建景点（admin）
    
    Args:
        data: 景点创建数据
        current_user: 当前认证的管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含创建景点信息的响应
        
    Raises:
        HTTPException: 403 如果权限不足
    """
    spot = await KnowledgeService.create_spot(db, data)
    
    return {
        "code": 200,
        "data": {
            "id": spot.id,
            "name": spot.name,
            "city": spot.city,
            "category": spot.category,
            "description": spot.description,
            "tags": spot.tags,
            "avg_cost": spot.avg_cost,
            "duration": spot.duration,
            "open_time": spot.open_time,
            "rating": spot.rating,
            "vector_id": spot.vector_id,
            "created_at": spot.created_at.isoformat() if spot.created_at else None,
            "updated_at": spot.updated_at.isoformat() if spot.updated_at else None
        },
        "message": "创建景点成功",
        "error": None
    }


@router.put(
    "/spots/{spot_id}",
    response_model=dict,
    summary="更新景点",
    description="""
    更新指定景点信息（仅管理员）。
    
    需要在请求头中包含有效的JWT token（管理员权限）：
    - Authorization: Bearer <token>
    
    路径参数：
    - spot_id: 景点ID
    
    请求体（可选字段）：
    - name: 景点名称
    - city: 城市
    - category: 分类
    - description: 描述
    - tags: 标签列表
    - avg_cost: 平均花费
    - duration: 推荐游览时长
    - open_time: 开放时间
    - rating: 评分
    
    错误响应：
    - 401: 未授权
    - 403: 权限不足（需要管理员权限）
    - 404: 景点不存在
    - 422: 请求参数验证失败
    """
)
async def update_spot(
    spot_id: int,
    data: SpotUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新景点（admin）
    
    Args:
        spot_id: 景点ID
        data: 景点更新数据
        current_user: 当前认证的管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含更新后景点信息的响应
        
    Raises:
        HTTPException: 404 如果景点不存在
        HTTPException: 403 如果权限不足
    """
    spot = await KnowledgeService.update_spot(db, spot_id, data)
    
    return {
        "code": 200,
        "data": {
            "id": spot.id,
            "name": spot.name,
            "city": spot.city,
            "category": spot.category,
            "description": spot.description,
            "tags": spot.tags,
            "avg_cost": spot.avg_cost,
            "duration": spot.duration,
            "open_time": spot.open_time,
            "rating": spot.rating,
            "vector_id": spot.vector_id,
            "created_at": spot.created_at.isoformat() if spot.created_at else None,
            "updated_at": spot.updated_at.isoformat() if spot.updated_at else None
        },
        "message": "更新景点成功",
        "error": None
    }


@router.delete(
    "/spots/{spot_id}",
    response_model=dict,
    summary="删除景点",
    description="""
    删除指定景点（仅管理员）。
    
    需要在请求头中包含有效的JWT token（管理员权限）：
    - Authorization: Bearer <token>
    
    路径参数：
    - spot_id: 景点ID
    
    错误响应：
    - 401: 未授权
    - 403: 权限不足（需要管理员权限）
    - 404: 景点不存在
    """
)
async def delete_spot(
    spot_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除景点（admin）
    
    Args:
        spot_id: 景点ID
        current_user: 当前认证的管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含成功消息的响应
        
    Raises:
        HTTPException: 404 如果景点不存在
        HTTPException: 403 如果权限不足
    """
    await KnowledgeService.delete_spot(db, spot_id)
    
    return {
        "code": 200,
        "data": None,
        "message": "删除景点成功",
        "error": None
    }


@router.post(
    "/spots/bulk",
    response_model=dict,
    summary="批量导入景点",
    description="""
    批量导入景点（仅管理员）。
    
    需要在请求头中包含有效的JWT token（管理员权限）：
    - Authorization: Bearer <token>
    
    请求体为 JSON 数组格式的景点数据。
    单条失败不阻断整批，返回结果包含成功/失败数量。
    
    错误响应：
    - 401: 未授权
    - 403: 权限不足
    - 422: 请求参数验证失败
    """
)
async def bulk_import_spots(
    spots_data: List[Dict[str, Any]] = Body(..., description="景点数据数组"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """批量导入景点（admin）
    
    Args:
        spots_data: 景点数据数组
        current_user: 当前认证的管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含导入结果的响应
    """
    result = await KnowledgeService.bulk_import_spots(db, spots_data)
    
    return {
        "code": 200,
        "data": result,
        "message": f"批量导入完成：成功 {result['success']} 条，失败 {result['failed']} 条",
        "error": None,
    }
