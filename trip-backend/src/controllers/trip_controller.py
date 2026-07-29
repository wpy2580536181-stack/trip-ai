"""Trip controller — 行程推荐端点（对齐 Node.js tripController.ts）

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
from src.middleware.rate_limiter import recommend_rate_limiter
from src.middleware.concurrency_guard import concurrency_guard_dependency
from src.middleware.token_budget_guard import token_budget_guard_dependency
from src.models.user import User
from src.schemas.trip import RecommendRequest
from src.services.trip_service import trip_service

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
    - progress: 阶段进度（research/plan/review/save + start/done，供前端实时步骤展示）
    - tool_start / tool_end: Research 并行工具事件（带 key：attractions/food/hotels/weather/distance）
    - heartbeat: 空闲时每 3s 发送心跳（keep-alive）
    - complete: 行程生成完成，包含完整结果数据
    - error: 生成失败
    """
    # 1. Start event
    yield f"data: {json.dumps({'type': 'start', 'city': body.city, 'days': body.days, 'budget': body.budget}, ensure_ascii=False)}\n\n"

    # 2. 事件队列：Agent 管线的进度/工具事件透传给前端（complete/error 由本函数统一发）
    queue: asyncio.Queue = asyncio.Queue()
    _forward_types = {"progress", "tool_start", "tool_end"}

    async def on_event(event: dict):
        if event.get("type") in _forward_types:
            await queue.put(event)

    async def call_recommend():
        try:
            result = await trip_service.recommend(
                city=body.city,
                budget=body.budget,
                days=body.days,
                user_id=user_id,
                departure_city=body.departure_city,
                on_event=on_event,
            )
            return result, None
        except Exception as e:
            return None, str(e)

    task = asyncio.create_task(call_recommend())
    last_heartbeat = time.time()

    while True:
        # 优先透传进度事件
        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            last_heartbeat = time.time()
            continue
        except asyncio.TimeoutError:
            pass

        if task.done():
            # 刷干残留事件后再发终态
            while not queue.empty():
                event = queue.get_nowait()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            result, error = task.result()
            if error:
                yield f"data: {json.dumps({'type': 'error', 'error': error}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'complete', 'data': result}, ensure_ascii=False)}\n\n"
            break

        # 空闲时每 3s 发心跳
        now = time.time()
        if now - last_heartbeat >= 3.0:
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
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


