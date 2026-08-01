"""Trip Python Backend - FastAPI Application Entry Point"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

import os
import time
import uuid
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import structlog
from src.config.settings import settings
from src.utils.logger import setup_logging, trip_log

from src.middleware.rate_limiter import GlobalRateLimitMiddleware
from src.middleware.idempotency import IdempotencyMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理"""
    setup_logging()
    trip_log.info("Trip Python Backend starting", port=settings.port)
    
    # 初始化数据库连接
    from src.config.database import init_db
    await init_db()
    trip_log.info("Database initialized")

    # 初始化 Redis 连接（失败时降级为内存模式）
    from src.config.redis_client import init_redis, close_redis, is_redis_available
    await init_redis()

    # 初始化 arq 任务队列 pool（依赖 Redis；Redis 不可用时 task_queue 自动降级）
    # init_redis 失败时会抛错，到不了这里；所以不再做冗余 is_redis_available() 检查
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        from src.services.task_queue import get_task_queue
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        get_task_queue().attach_arq_pool(pool)
        trip_log.info("Arq task queue pool initialized")
    except Exception as e:
        trip_log.warning(arq_pool_init_failed=str(e), msg="arq pool init 失败，task_queue 走降级")

    # 启动告警调度器（可选，配置不当时不启动）
    from src.services.alert import alert_scheduler
    alert_scheduler.start()

    # 后台预热 Embedding 模型（fail-closed 默认降级，加载成功才恢复向量检索）。
    # 不阻塞启动；HF 镜像不可达时后台静默失败，主流程走字面/全文检索。
    try:
        from src.services.agent.agent_engine import get_agent_engine
        await get_agent_engine().start_embedder_warmup()
    except Exception as e:
        trip_log.warning(embedder_warmup_kickoff_failed=str(e))

    yield

    # 停止告警调度器
    alert_scheduler.stop()

    # 关闭 arq pool（如已初始化）
    try:
        from src.services.task_queue import get_task_queue
        tq = get_task_queue()
        if tq._arq_pool is not None:
            close_method = getattr(tq._arq_pool, "aclose", None) or tq._arq_pool.close
            res = close_method()
            if hasattr(res, "__await__"):
                await res
    except Exception as e:
        trip_log.warning(arq_pool_close_failed=str(e), msg="arq pool close 失败")

    # 关闭 Redis 连接
    await close_redis()

    # 关闭数据库连接
    from src.config.database import close_db
    await close_db()
    trip_log.info("Trip Python Backend shutdown")


# ---------------------------------------------------------------------------
# 请求 ID 中间件（原生 ASGI，透传不缓冲，兼容 SSE）
# ---------------------------------------------------------------------------


class RequestIDMiddleware:
    """为每次请求绑定 request_id，贯穿日志与出站调用头。

    - 优先复用客户端下发的 ``x-request-id``，否则生成 uuid
    - 通过 structlog contextvars 绑定，使本次请求所有日志自动携带 request_id
    - 在响应头回写 ``x-request-id``，便于前端/网关串联
    - 请求结束（含异常）清除上下文，避免串号
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._read_request_id(scope)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                if not any(h[0].lower() == b"x-request-id" for h in headers):
                    headers.append((b"x-request-id", request_id.encode("utf-8")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            structlog.contextvars.clear_contextvars()

    @staticmethod
    def _read_request_id(scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id":
                rid = value.decode("utf-8", "ignore").strip()
                if rid:
                    return rid
        return uuid.uuid4().hex


def create_app() -> FastAPI:
    """FastAPI 应用工厂"""
    app = FastAPI(
        title="Trip AI Travel Planner",
        description="Python backend for AI-powered travel planning",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # GZip 响应压缩中间件（最小 1KB，不影响 SSE 流式响应）
    # 注意：Starlette 中间件倒序执行，GZip 需最先注册以成为最外层包装
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    
    # CORS 中间件（需在路由前注册）
    setup_cors(app)
    
    # 全局限流中间件（所有 /api/* 请求），阈值读 settings（默认 2000 次/分钟，
    # 可通过环境变量 RATE_LIMIT_GLOBAL_MAX 覆盖，压测/eval 时临时调高）
    app.add_middleware(
        GlobalRateLimitMiddleware,
        max_requests=settings.rate_limit_global_max,
        window_seconds=60,
    )
    
    # 幂等性中间件：仅对 recommend 路径生效
    # 不应用到 chat（SSE 流式响应不能被 BaseHTTPMiddleware 缓冲）
    app.add_middleware(
        IdempotencyMiddleware,
        path_prefixes=["/api/trip/recommend"],
    )

    # 请求 ID 中间件：生成/透传 x-request-id，绑定 structlog 上下文，全链路日志关联。
    # 注册在最外层（最后 add），确保 CORS / 限流 / 幂等 等下游中间件日志均带 request_id；
    # 采用原生 ASGI 透传实现，不缓冲响应体，兼容 SSE 流式接口。
    app.add_middleware(RequestIDMiddleware)

    # Prometheus metrics 中间件（M5 新增，ASGI 实现兼容 SSE）
    # 注册在 RequestID 之后 → 更外层 → 涵盖所有请求（含 /health、/metrics 自身已排除）
    from src.middleware.prom_metrics import PrometheusMiddleware
    app.add_middleware(PrometheusMiddleware)

    # 注册异常处理器
    from src.middleware.exception_handlers import setup_exception_handlers
    setup_exception_handlers(app)
    
    # 注册路由（统一 /api 前缀，与 Node.js 版本一致）
    from src.controllers.user_controller import router as user_router
    app.include_router(user_router, prefix="/api")
    
    from src.controllers.conversation_controller import router as conversation_router
    app.include_router(conversation_router, prefix="/api")
    
    from src.controllers.history_controller import router as history_router
    app.include_router(history_router, prefix="/api")
    
    from src.controllers.knowledge_controller import router as knowledge_router
    app.include_router(knowledge_router, prefix="/api")
    
    from src.controllers.feedback_controller import router as feedback_router
    app.include_router(feedback_router, prefix="/api")
    
    from src.controllers.admin_controller import router as admin_router
    app.include_router(admin_router, prefix="/api")
    
    from src.controllers.chat_controller import router as chat_router
    app.include_router(chat_router, prefix="/api")
    
    from src.controllers.trip_controller import router as trip_router
    app.include_router(trip_router, prefix="/api")

    from src.controllers.commute_controller import router as commute_router
    app.include_router(commute_router, prefix="/api")
    
    # 健康检查端点（负载均衡器用，不加 /api 前缀）
    @app.get("/health")
    async def health_check():
        return PlainTextResponse("OK")

    # Prometheus metrics 抓取端点（M5 新增，K8s Prometheus 自动配置 scrape）
    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        from starlette.responses import Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
    # 详细健康检查端点（监控用）
    @app.get("/health/detail")
    async def health_detail():
        import resource
        mem = resource.getrusage(resource.RUSAGE_SELF)
        status = {
            "status": "ok",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
            "uptime": time.process_time(),
            "memory": {
                "rss": mem.ru_maxrss,
            },
            "checks": {},
        }
        return JSONResponse(status)
    
    return app


def setup_cors(app: FastAPI):
    """CORS 配置（严格按架构文档 8.4 节）"""
    allowed_origins = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:3000",
    ]
    if settings.cors_demo:
        allowed_origins.append("null")
    
    # 合并 env 配置的 origins
    if settings.cors_origin:
        for origin in settings.cors_origin.split(","):
            origin = origin.strip()
            if origin and origin not in allowed_origins:
                allowed_origins.append(origin)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(set(allowed_origins)),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-Stream-Id", "Last-Event-ID", "x-request-id"],
        max_age=86400,
    )


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.node_env == "development",
    )
