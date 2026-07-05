"""Chat controller (AI对话接口 — SSE 断点续传 + TripService 增强版)

对齐 Node.js tripController.ts 中的 chat 端点：
- SSE 流式响应（event: delta / complete / error）
- 增量持久化（每 3s flush 到数据库）
- 对话压缩触发
- 关键决策记录
- Token 用量回传（complete 事件携带 usage）
- 心跳机制（每 15s 发送 heartbeat）
- SSE 断点续传（X-Stream-Id + Last-Event-ID）
"""

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.middleware.auth import get_current_user
from src.middleware.rate_limiter import chat_rate_limiter
from src.middleware.concurrency_guard import concurrency_guard_dependency
from src.middleware.token_budget_guard import token_budget_guard_dependency
from src.models.user import User
from src.schemas.trip import ChatRequest
from src.services.trip_service import trip_service
from src.utils.stream import (
    create_resumable_stream,
    resume_stream,
    StreamNotFoundError,
    StreamForbiddenError,
    StreamBadRequestError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trip", tags=["Chat"])


async def _stream_with_release(
    stream: AsyncGenerator[str, None],
    request: Request,
) -> AsyncGenerator[str, None]:
    """包装 SSE 流，在流结束后释放并发信号量。"""
    try:
        async for chunk in stream:
            yield chunk
    finally:
        release = getattr(request.state, "_concurrency_release", None)
        if release:
            try:
                await release()
            except Exception as e:
                logger.warning(f"[Chat] Concurrency release error: {e}")


@router.post("/chat")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    _rate_limit: None = Depends(chat_rate_limiter),
    _token_budget: None = Depends(token_budget_guard_dependency),
    _concurrency: None = Depends(concurrency_guard_dependency),
):
    """AI 对话接口（SSE 流式响应 + 断点续传）

    支持 SSE 断点续传：
    - 正常请求：创建新流，返回 X-Stream-Id 响应头
    - 续传请求：携带 X-Stream-Id + Last-Event-ID 请求头，重发缺失 events

    Args:
        request: FastAPI 请求（用于释放并发信号量 + 读取续传头）
        body: 请求数据（message + conversationId）
        current_user: 当前登录用户

    Returns:
        StreamingResponse: SSE 事件流
    """
    # ---- 续传路径：X-Stream-Id + Last-Event-ID ----
    stream_id = request.headers.get("X-Stream-Id")
    last_event_id_header = request.headers.get("Last-Event-ID")

    if stream_id and last_event_id_header:
        try:
            last_seq = int(last_event_id_header)
        except (ValueError, TypeError):
            return StreamingResponse(
                iter(['event: error\ndata: {"error":"Last-Event-ID 必须是非负整数"}\n\n']),
                media_type="text/event-stream",
                status_code=400,
            )

        if last_seq < 0:
            return StreamingResponse(
                iter(['event: error\ndata: {"error":"Last-Event-ID 必须是非负整数"}\n\n']),
                media_type="text/event-stream",
                status_code=400,
            )

        try:
            gen = resume_stream(
                stream_id=stream_id,
                last_seq=last_seq,
                user_id=str(current_user.id),
            )
            return StreamingResponse(
                _stream_with_release(gen, request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Stream-Id": stream_id,
                },
            )
        except StreamNotFoundError:
            return StreamingResponse(
                iter(['event: error\ndata: {"error":"stream 不存在或已过期"}\n\n']),
                media_type="text/event-stream",
                status_code=404,
            )
        except StreamForbiddenError:
            return StreamingResponse(
                iter(['event: error\ndata: {"error":"无权访问此 stream"}\n\n']),
                media_type="text/event-stream",
                status_code=403,
            )
        except StreamBadRequestError as e:
            return StreamingResponse(
                iter([f'event: error\ndata: {{"error":"{str(e)}"}}\n\n']),
                media_type="text/event-stream",
                status_code=400,
            )

    # ---- 正常流式路径 ----
    return StreamingResponse(
        _stream_with_release(
            create_resumable_stream(
                user_id=str(current_user.id),
                conversation_id=str(body.conversation_id) if body.conversation_id else "pending",
                source=trip_service.chat_stream(
                    user_id=current_user.id,
                    message=body.message,
                    conversation_id=body.conversation_id,
                ),
            ),
            request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
