"""幂等性中间件。

针对 POST 请求，检查 Idempotency-Key 请求头。
如果相同的 key 已经处理过，直接返回缓存的响应。
对齐 Node.js trip-server 的 createIdempotencyMiddleware 实现。
"""

import time
import json
import logging
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

DEFAULT_TTL_S = 3600  # 1 小时
CLEANUP_INTERVAL_S = 60


# ─── 缓存存储 ───


class CachedResponse:
    """缓存的响应。"""
    __slots__ = ("status_code", "body", "created_at")

    def __init__(self, status_code: int, body: str, created_at: float):
        self.status_code = status_code
        self.body = body
        self.created_at = created_at


class MemoryIdempotencyStore:
    """内存幂等性存储（带 TTL 和惰性清理）。"""

    def __init__(self, ttl_s: float = DEFAULT_TTL_S):
        self._data: dict[str, CachedResponse] = {}
        self._ttl_s = ttl_s

    async def get(self, key: str) -> Optional[CachedResponse]:
        entry = self._data.get(key)
        if not entry:
            return None
        if time.time() - entry.created_at >= self._ttl_s:
            del self._data[key]
            return None
        return entry

    async def set(self, key: str, entry: CachedResponse) -> None:
        self._data[key] = entry

    def cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._data.items() if now - v.created_at >= self._ttl_s]
        for k in expired:
            del self._data[k]


# ─── 幂等性中间件 ───


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """幂等性中间件（BaseHTTPMiddleware）。

    对齐 Node.js 的 createIdempotencyMiddleware：
    - 仅拦截 POST 请求
    - 检查 Idempotency-Key 请求头
    - 命中缓存时直接返回
    - 未命中时执行请求并缓存 2xx 响应

    用法::

        from src.middleware.idempotency import idempotency_middleware
        router = APIRouter()
        router.middleware(idempotency_middleware)
    """

    def __init__(
        self,
        app,
        ttl_s: float = DEFAULT_TTL_S,
        header_name: str = "idempotency-key",
        store: Optional[MemoryIdempotencyStore] = None,
        path_prefixes: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self._store = store or MemoryIdempotencyStore(ttl_s)
        self._header_name = header_name.lower()
        # 可选路径前缀过滤（为空则匹配所有 POST）
        self._path_prefixes = path_prefixes

    async def dispatch(self, request: Request, call_next) -> Response:
        # 仅拦截 POST
        if request.method != "POST":
            return await call_next(request)

        # 路径前缀过滤
        if self._path_prefixes:
            if not any(request.url.path.startswith(p) for p in self._path_prefixes):
                return await call_next(request)

        # 检查 Idempotency-Key 请求头
        raw_key = request.headers.get(self._header_name)
        if not raw_key:
            return await call_next(request)

        # 构建 full key: userId:rawKey
        user = getattr(request.state, "user", None)
        user_id = getattr(user, "id", None) if user else None
        full_key = f"{user_id or 'anonymous'}:{raw_key}"

        # 检查缓存
        cached = await self._store.get(full_key)
        if cached:
            logger.debug(f"[Idempotency] Cache hit: {full_key}")
            return JSONResponse(
                status_code=cached.status_code,
                content=json.loads(cached.body),
            )

        # 执行请求并捕获响应
        response = await call_next(request)

        # 只缓存 2xx 响应
        if 200 <= response.status_code < 300:
            # 读取响应体
            body_chunks = []
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    body_chunks.append(chunk)
                else:
                    body_chunks.append(chunk.encode("utf-8"))
            body_bytes = b"".join(body_chunks)

            # 尝试解析为 JSON 并缓存
            try:
                body_str = body_bytes.decode("utf-8")
                json.loads(body_str)  # 验证是合法 JSON
                await self._store.set(
                    full_key,
                    CachedResponse(
                        status_code=response.status_code,
                        body=body_str,
                        created_at=time.time(),
                    ),
                )
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # 非 JSON 响应不缓存

            # 重新构建 Response（body_iterator 已被消费）
            return Response(
                content=body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response


# ─── 预置中间件工厂 ───


def create_idempotency_middleware(app, **kwargs) -> IdempotencyMiddleware:
    """创建幂等性中间件实例。"""
    return IdempotencyMiddleware(app, **kwargs)
