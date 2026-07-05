"""Trip Python Backend - FastAPI Application Entry Point"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

import os
import time

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
    from src.config.redis_client import init_redis, close_redis
    await init_redis()
    
    # 启动告警调度器（可选，配置不当时不启动）
    from src.services.alert import alert_scheduler
    alert_scheduler.start()
    
    yield
    
    # 停止告警调度器
    alert_scheduler.stop()
    
    # 关闭 Redis 连接
    await close_redis()

    # 关闭数据库连接
    from src.config.database import close_db
    await close_db()
    trip_log.info("Trip Python Backend shutdown")


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
    
    # 全局限流中间件：2000 次/分钟（所有 /api/* 请求，eval 测试临时放宽）
    app.add_middleware(
        GlobalRateLimitMiddleware,
        max_requests=2000,
        window_seconds=60,
    )
    
    # 幂等性中间件：仅对 recommend / optimize 路径生效
    # 不应用到 chat（SSE 流式响应不能被 BaseHTTPMiddleware 缓冲）
    app.add_middleware(
        IdempotencyMiddleware,
        path_prefixes=["/api/trip/recommend", "/api/trip/optimize"],
    )
    
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
    
    from src.controllers.stats_controller import router as stats_router
    app.include_router(stats_router, prefix="/api")
    
    from src.controllers.admin_controller import router as admin_router
    app.include_router(admin_router, prefix="/api")
    
    from src.controllers.chat_controller import router as chat_router
    app.include_router(chat_router, prefix="/api")
    
    from src.controllers.trip_controller import router as trip_router
    app.include_router(trip_router, prefix="/api")
    
    # 健康检查端点（负载均衡器用，不加 /api 前缀）
    @app.get("/health")
    async def health_check():
        return PlainTextResponse("OK")
    
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
