"""Trip controller — 行程推荐 & 优化端点（对齐 Node.js tripController.ts）

chat 端点在 chat_controller.py 中（已使用 trip_service 增强）。
"""

import asyncio
import json
import logging
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

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
async def _recommend_stream(
    body: RecommendRequest,
    user_id: int,
) -> AsyncGenerator[str, None]:
    """行程推荐的 SSE 流式生成器。

    事件类型：
    - start: 连接建立成功，包含请求参数
    - heartbeat: 每 3s 发送心跳（keep-alive）
    - complete: 行程生成完成，包含完整结果数据
    - error: 生成失败
    """
    # 1. Start event
    yield f"event: start\ndata: {json.dumps({'city': body.city, 'days': body.days, 'budget': body.budget}, ensure_ascii=False)}\n\n"

    # 2. Call recommend and send heartbeats concurrently
    async def call_recommend():
        try:
            result = await trip_service.recommend(
                city=body.city,
                budget=body.budget,
                days=body.days,
                user_id=user_id,
                departure_city=body.departure_city,
            )
            return result, None
        except Exception as e:
            return None, str(e)

    task = asyncio.create_task(call_recommend())
    last_heartbeat = time.time()

    while True:
        done, _ = await asyncio.wait([task], timeout=3.0)
        if task in done:
            result, error = task.result()
            if error:
                yield f"event: error\ndata: {json.dumps({'error': error}, ensure_ascii=False)}\n\n"
            else:
                yield f"event: complete\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
            break
        # Send heartbeat every 3s
        now = time.time()
        if now - last_heartbeat >= 3.0:
            yield "event: heartbeat\ndata: {}\n\n"
            last_heartbeat = now


@router.post("/recommend-stream")
async def recommend_stream(
    request: Request,
    body: RecommendRequest,
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(recommend_rate_limiter),
    _token_budget: None = Depends(token_budget_guard_dependency),
    _concurrency: None = Depends(concurrency_guard_dependency),
):
    """行程推荐 SSE 流式接口。

    与 /recommend 不同，此接口返回 SSE 事件流：
    - 立即响应（无需长时间等待）
    - 支持前端显示生成进度
    - 包含心跳保活机制

    Args:
        body: 推荐请求参数
        current_user: 当前登录用户

    Returns:
        StreamingResponse: SSE 事件流
    """
    async def _stream_with_release():
        try:
            async for event in _recommend_stream(body, current_user.id):
                yield event
        finally:
            release = getattr(request.state, "_concurrency_release", None)
            if release:
                try:
                    await release()
                except Exception:
                    pass

    return StreamingResponse(
        _stream_with_release(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
