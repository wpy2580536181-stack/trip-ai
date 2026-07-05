"""Trip controller — 行程推荐 & 优化端点（对齐 Node.js tripController.ts）

chat 端点在 chat_controller.py 中（已使用 trip_service 增强）。
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from src.middleware.auth import get_current_user
from src.middleware.rate_limiter import recommend_rate_limiter, optimize_rate_limiter
from src.middleware.concurrency_guard import concurrency_guard_dependency
from src.middleware.token_budget_guard import token_budget_guard_dependency
from src.models.user import User
from src.schemas.trip import RecommendRequest, OptimizeRequest
from src.services.trip_service import trip_service
from src.services.optimize_service import optimize_trip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trip", tags=["Trip"])


@router.post("/recommend")
async def recommend(
    request: Request,
    body: RecommendRequest,
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(recommend_rate_limiter),
    _token_budget: None = Depends(token_budget_guard_dependency),
    _concurrency: None = Depends(concurrency_guard_dependency),
):
    """行程推荐接口。

    Args:
        body: 推荐请求参数
        current_user: 当前登录用户

    Returns:
        行程推荐结果
    """
    try:
        result = await trip_service.recommend(
            city=body.city,
            budget=body.budget,
            days=body.days,
            user_id=current_user.id,
            departure_city=body.departure_city,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"行程推荐失败: {e}")
        raise HTTPException(status_code=500, detail="行程推荐失败，请稍后重试")
    finally:
        release = getattr(request.state, "_concurrency_release", None)
        if release:
            await release()
            request.state._concurrency_release = None


@router.post("/optimize")
async def optimize(
    request: Request,
    body: OptimizeRequest,
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(optimize_rate_limiter),
    _token_budget: None = Depends(token_budget_guard_dependency),
    _concurrency: None = Depends(concurrency_guard_dependency),
):
    """行程优化接口。

    Args:
        body: 优化请求参数
        current_user: 当前登录用户

    Returns:
        优化后的行程结果
    """
    try:
        result = await optimize_trip(
            trip_id=body.trip_id,
            instruction=body.instruction or "",
            user_id=current_user.id,
        )
        return result
    except ValueError as e:
        err_msg = str(e)
        if "不存在" in err_msg:
            raise HTTPException(status_code=404, detail=err_msg)
        raise HTTPException(status_code=500, detail=err_msg)
    except Exception as e:
        logger.error(f"行程优化失败: {e}")
        raise HTTPException(status_code=500, detail="行程优化失败，请稍后重试")
    finally:
        release = getattr(request.state, "_concurrency_release", None)
        if release:
            await release()
            request.state._concurrency_release = None
