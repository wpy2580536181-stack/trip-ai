"""并发守卫中间件。

将 services/agent/semaphore.py 的 ConcurrencyGuard 包装为 FastAPI 中间件/依赖。
对齐 Node.js trip-server 的 concurrencyGuard.ts。
"""

import logging

from fastapi import Request, HTTPException
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.services.agent.semaphore import concurrency_guard

logger = logging.getLogger(__name__)


async def concurrency_guard_dependency(request: Request) -> None:
    """并发守卫依赖（FastAPI Depends）。

    在 /api/trip/* 的 chat / recommend / optimize 路由上使用。
    超限时返回 429。

    对于非流式端点，release 自动通过 BackgroundTask 执行。
    对于流式端点（SSE），release 保存在 request.state 中，
    由流生成器的 finally 块手动调用。

    用法::

        @router.post("/chat")
        async def chat(_: None = Depends(concurrency_guard_dependency)):
            ...
    """
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None) if user else 0

    success, release = await concurrency_guard.try_acquire(user_id or 0)

    if not success:
        raise HTTPException(
            status_code=429,
            detail={"code": 429, "error": "系统繁忙，请稍后再试"},
        )

    # 保存 release 函数，供流式端点在 finally 中调用
    request.state._concurrency_release = release

    # 为非流式端点注册 BackgroundTask（响应发送后释放）
    request.state._concurrency_background_release = BackgroundTask(_safe_release, release)


async def _safe_release(release) -> None:
    """安全释放并发信号量。"""
    try:
        await release()
    except Exception as e:
        logger.warning(f"[ConcurrencyGuard] Release error: {e}")


class ConcurrencyGuardMiddleware(BaseHTTPMiddleware):
    """并发守卫中间件（BaseHTTPMiddleware 版本）。

    自动在请求处理前后获取/释放并发信号量。
    适用于非流式端点。流式端点请使用 Depends 版本。

    用法::

        router = APIRouter()
        router.add_middleware(ConcurrencyGuardMiddleware)
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        user = getattr(request.state, "user", None)
        user_id = getattr(user, "id", None) if user else 0

        success, release = await concurrency_guard.try_acquire(user_id or 0)

        if not success:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"code": 429, "error": "系统繁忙，请稍后再试"},
            )

        try:
            response = await call_next(request)
            return response
        finally:
            await _safe_release(release)


def get_concurrency_stats() -> dict:
    """获取并发统计信息（调试用）。"""
    return {
        "global_available": concurrency_guard._global._value,
        "active_users": len(concurrency_guard._per_user),
    }
