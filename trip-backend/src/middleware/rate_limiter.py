"""限流中间件。

基于滑动窗口的限流器，支持内存和 Redis 双模式。
对齐 Node.js trip-server 的 createLimiter 实现。
"""

import time
import math
import logging
from typing import Callable, Optional

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_S = 60  # 内存存储清理间隔（秒）


# ─── 存储层 ───


class RateLimitEntry:
    """限流条目。"""
    __slots__ = ("count", "reset_at")

    def __init__(self, count: int, reset_at: float):
        self.count = count
        self.reset_at = reset_at


class MemoryStore:
    """内存限流存储（固定窗口 + 惰性清理）。"""

    def __init__(self):
        self._data: dict[str, RateLimitEntry] = {}

    async def increment(self, key: str, window_s: float) -> tuple[int, float]:
        """原子递增计数。

        Returns:
            (当前计数, 窗口重置时间戳)
        """
        now = time.time()
        entry = self._data.get(key)

        if not entry or now >= entry.reset_at:
            reset_at = now + window_s
            self._data[key] = RateLimitEntry(count=1, reset_at=reset_at)
            return 1, reset_at

        entry.count += 1
        return entry.count, entry.reset_at

    async def reset_key(self, key: str) -> None:
        self._data.pop(key, None)

    def cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._data.items() if now >= v.reset_at]
        for k in expired:
            del self._data[k]


class RedisStore:
    """Redis 限流存储（INCR + EXPIRE 原子操作，使用异步 Redis 客户端）。"""

    def __init__(self, redis_client):
        self._client = redis_client

    async def increment(self, key: str, window_s: float) -> tuple[int, float]:
        reset_at = time.time() + window_s
        ttl = math.ceil(window_s)

        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        count = results[0] or 1
        return count, reset_at

    async def reset_key(self, key: str) -> None:
        await self._client.delete(key)


def _create_store():
    """根据配置创建存储后端。优先 Redis，降级内存。"""
    try:
        from src.config.redis_client import get_redis, is_redis_available
        if is_redis_available():
            r = get_redis()
            logger.info("[RateLimiter] Using Redis store")
            return RedisStore(r)
    except Exception:
        pass

    logger.info("[RateLimiter] Using in-memory store")
    return MemoryStore()


# ─── 限流依赖（Depends 模式） ───


class RateLimiter:
    """基于滑动窗口的限流器，用作 FastAPI Depends。

    用法::

        chat_limiter = RateLimiter(max_requests=20, window_seconds=60,
                                   message="对话请求过于频繁，请稍后再试")

        @router.post("/chat")
        async def chat(_: None = Depends(chat_limiter)):
            ...
    """

    def __init__(
        self,
        max_requests: int = 20,
        window_seconds: int = 60,
        key_func: Optional[Callable[[Request], str]] = None,
        message: str = "请求过于频繁，请稍后再试",
        store=None,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.key_func = key_func or self._default_key
        self.message = message
        self.store = store or _create_store()

    @staticmethod
    def _default_key(request: Request) -> str:
        """默认 key：优先使用 user ID，否则使用 client IP。"""
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "id"):
            return str(user.id)
        return request.client.host if request.client else "anonymous"

    async def __call__(self, request: Request) -> None:
        key = self.key_func(request)
        count, reset_at = await self.store.increment(key, self.window_seconds)

        # 设置限流响应头（通过 request.state 传递，由响应阶段写入）
        request.state.rate_limit_headers = {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(max(0, self.max_requests - count)),
            "X-RateLimit-Reset": str(math.ceil(reset_at)),
        }

        if count > self.max_requests:
            raise HTTPException(
                status_code=429,
                detail={"code": 429, "error": self.message},
            )


# ─── 全局 ASGI 限流中间件 ───


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """全局限流 ASGI 中间件（应用于所有 /api/* 请求）。

    对齐 Node.js: app.use('/api', createLimiter({ windowMs: 60000, max: 200 }))
    """

    def __init__(self, app, max_requests: int = 200, window_seconds: int = 60):
        super().__init__(app)
        self.limiter = RateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
            message="系统繁忙，请稍后再试",
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        # 只对 /api 路径限流
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        try:
            await self.limiter(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
            )

        response = await call_next(request)

        # 注入限流响应头
        headers = getattr(request.state, "rate_limit_headers", None)
        if headers:
            for k, v in headers.items():
                response.headers[k] = v

        return response


# ─── 预置限流器实例（对齐 Node.js 配置，支持环境变量覆盖） ───

# 引入配置（延迟导入，避免循环依赖）
from src.config.settings import settings as _s

# 全局：200 次/分钟（ASGI 中间件，在 main.py 注册）
global_rate_limiter_config = {
    "max_requests": _s.rate_limit_global_max,
    "window_seconds": 60,
}

# 认证（/api/user/*）：从 settings 读取
auth_rate_limiter = RateLimiter(
    max_requests=_s.rate_limit_auth_max,
    window_seconds=_s.rate_limit_auth_window,
    message="请求过于频繁，请稍后再试",
)

# 反馈（/api/feedback/*）：30 次/1 小时
feedback_rate_limiter = RateLimiter(
    max_requests=_s.rate_limit_feedback_max,
    window_seconds=60 * 60,
    message="反馈提交过于频繁，请稍后再试",
)

# 知识库（/api/knowledge/* 写操作）：100 次/1 分钟
knowledge_rate_limiter = RateLimiter(
    max_requests=_s.rate_limit_knowledge_max,
    window_seconds=60,
    message="知识库请求过于频繁，请稍后再试",
)

# Chat（/api/trip/chat）
chat_rate_limiter = RateLimiter(
    max_requests=_s.rate_limit_chat_max,
    window_seconds=60,
    message="对话请求过于频繁，请稍后再试",
)

# Recommend（/api/trip/recommend）
recommend_rate_limiter = RateLimiter(
    max_requests=_s.rate_limit_recommend_max,
    window_seconds=60,
    message="行程推荐请求过于频繁，请稍后再试",
)

# Optimize（/api/trip/optimize）
optimize_rate_limiter = RateLimiter(
    max_requests=_s.rate_limit_optimize_max,
    window_seconds=60,
    message="行程优化请求过于频繁，请稍后再试",
)
