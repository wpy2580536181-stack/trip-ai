"""Trip Python Backend - FastAPI Application Entry Point"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings
from src.utils.logger import setup_logging, trip_log


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理"""
    setup_logging()
    trip_log.info("Trip Python Backend starting", port=settings.port)
    
    # 初始化数据库连接
    from src.config.database import init_db
    await init_db()
    trip_log.info("Database initialized")
    
    yield
    
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
    
    # CORS 中间件（需在路由前注册）
    setup_cors(app)
    
    # 注册异常处理器
    from src.middleware.exception_handlers import setup_exception_handlers
    setup_exception_handlers(app)
    
    # 注册路由
    from src.controllers.user_controller import router as user_router
    app.include_router(user_router)
    
    from src.controllers.conversation_controller import router as conversation_router
    app.include_router(conversation_router)
    
    from src.controllers.history_controller import router as history_router
    app.include_router(history_router)
    
    from src.controllers.knowledge_controller import router as knowledge_router
    app.include_router(knowledge_router)
    
    # 健康检查端点
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "0.1.0"}
    
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
