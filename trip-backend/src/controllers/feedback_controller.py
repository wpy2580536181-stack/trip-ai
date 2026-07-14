"""Feedback controller (HTTP handlers)"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import date, timedelta

from src.config.database import get_db
from src.middleware.auth import get_current_user, require_admin
from src.middleware.rate_limiter import feedback_rate_limiter
from src.schemas.user import FeedbackCreate, FeedbackResponse
from src.services.feedback_service import FeedbackService
from src.models.user import User


router = APIRouter(
    prefix="/feedback",
    tags=["Feedback"],
    dependencies=[Depends(feedback_rate_limiter)],
)


@router.get("", response_model=dict, summary="获取反馈列表")
async def get_feedbacks(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize", description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的反馈列表
    
    Args:
        page: 页码
        page_size: 每页条数
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 包含反馈列表的响应
    """
    try:
        result = await FeedbackService.get_user_feedbacks(db, current_user.id, page, page_size)
        return {
            "code": 200,
            "data": result,
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("", response_model=dict, summary="提交反馈")
async def submit_feedback(
    data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """提交用户对消息的反馈（点赞/点踩）
    
    IDOR 防护：验证 message 存在 + 属于当前用户 + 仅 assistant 消息可评分
    防滥用：comment 截断 500 字符 + tags 限 10 个且每个 50 字符
    
    Args:
        data: 反馈数据（messageId, conversationId, rating, comment, tags）
        current_user: 当前登录用户
        db: 数据库会话
        
    Returns:
        dict: 包含反馈信息的响应
    """
    try:
        result = await FeedbackService.submit_feedback(db, current_user.id, data)
        return {
            "code": 200,
            "data": result,
            "message": "反馈提交成功",
            "error": None
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail={"code": 403, "error": str(e)})
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 400, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 500, "error": "提交失败"})


@router.get("/message/{message_id}", response_model=dict, summary="获取消息反馈统计")
async def get_message_stats(
    message_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单条消息的反馈统计
    
    Args:
        message_id: 消息ID
        db: 数据库会话
        
    Returns:
        dict: 包含反馈统计的响应
    """
    try:
        stats = await FeedbackService.get_message_stats(db, message_id)
        return {
            "code": 200,
            "data": stats,
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats", response_model=dict, summary="获取全局反馈统计（Admin）")
async def get_global_stats(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取全局反馈统计（admin only）
    
    Args:
        days: 统计天数（1-90）
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含全局统计的响应
    """
    try:
        stats = await FeedbackService.get_global_stats(db, days)
        return {
            "code": 200,
            "data": stats,
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 500, "error": "查询失败"})


@router.get("/list/{message_id}", response_model=dict, summary="单条消息反馈列表（Admin）")
async def list_for_message(
    message_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取某条消息的所有反馈列表（admin only）
    
    Args:
        message_id: 消息ID
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含反馈列表的响应
    """
    try:
        data = await FeedbackService.list_for_message(db, message_id)
        return {
            "code": 200,
            "data": data,
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 500, "error": "查询失败"})


@router.get("/admin/high-token-low-satisfaction", response_model=dict, summary="高 token 低满意度案例（Admin）")
async def get_high_token_low_satisfaction(
    days: int = Query(7, ge=1, le=90, description="查询最近天数"),
    limit: int = Query(20, ge=1, le=100, description="返回条数上限"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """高 token + 低满意度案例（admin dashboard 用）
    
    找出负反馈的 message，关联 token 使用量，按 token 降序返回 top N。
    
    Args:
        days: 查询最近天数
        limit: 返回条数上限
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 高 token 低满意度案例列表
    """
    try:
        data = await FeedbackService.get_high_token_low_satisfaction(db, days, limit)
        return {
            "code": 200,
            "data": data,
            "message": "获取成功",
            "error": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 500, "error": "查询失败"})


@router.get("/admin/daily-stats", response_model=dict, summary="每日统计趋势（Admin）")
async def get_daily_stats(
    start_date: Optional[str] = Query(None, alias="start_date", description="起始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, alias="end_date", description="结束日期 (YYYY-MM-DD)"),
    days: int = Query(30, ge=1, le=90, description="查询天数（当 start_date/end_date 未传时使用）"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """日维度统计（admin dashboard 趋势图）
    
    按日期分组统计反馈数据，含日期填充确保连续日期无间断。
    
    Args:
        start_date: 起始日期
        end_date: 结束日期
        days: 查询天数（当 start_date/end_date 未传时使用）
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 每日统计数据
    """
    try:
        # 解析日期参数
        if start_date and end_date:
            sd = date.fromisoformat(start_date)
            ed = date.fromisoformat(end_date)
        else:
            ed = date.today()
            sd = ed - timedelta(days=days - 1)

        data = await FeedbackService.get_daily_stats(db, sd, ed)
        return {
            "code": 200,
            "data": data,
            "message": "获取成功",
            "error": None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 400, "error": f"日期参数无效: {e}"})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 500, "error": "查询失败"})


@router.post("/admin/test-alert", response_model=dict, summary="触发告警检测（Admin，E2E 测试用）")
async def test_alert(
    current_user: User = Depends(require_admin),
):
    """触发一次告警检测（E2E 测试用，生产不应暴露）
    
    Args:
        current_user: 当前管理员用户
        
    Returns:
        dict: 告警检测结果
    """
    from src.services.alert import alert_scheduler
    
    try:
        result = await alert_scheduler.tick()
        return {
            "code": 200,
            "data": result,
            "message": "告警检测完成",
            "error": None
        }
    except Exception as e:
        return {
            "code": 200,
            "data": {"shouldAlert": False, "sent": False, "reason": str(e)},
            "message": "告警检测异常",
            "error": str(e)
        }


@router.post("/admin/convert-to-fixture", response_model=dict, summary="转换反馈为测试夹具（Admin）")
async def convert_to_fixture(
    body: dict = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """将反馈转换为测试夹具（Admin 功能）
    
    单条失败不阻断整批，错误汇总在 skipped[]
    
    Args:
        body: 请求体，含 feedbackIds 字段
        current_user: 当前管理员用户
        db: 数据库会话
        
    Returns:
        dict: 包含转换结果的响应
    """
    feedback_ids = body.get("feedbackIds")
    if not isinstance(feedback_ids, list) or len(feedback_ids) == 0:
        raise HTTPException(status_code=400, detail={"code": 400, "error": "feedbackIds 必填且为非空数组"})
    if len(feedback_ids) > 50:
        raise HTTPException(status_code=400, detail={"code": 400, "error": "最多 50 条"})

    try:
        result = await FeedbackService.convert_to_fixture(db, feedback_ids)
        return {
            "code": 200,
            "data": result,
            "message": "转换成功",
            "error": None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"code": 400, "error": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 500, "error": "转换失败"})
