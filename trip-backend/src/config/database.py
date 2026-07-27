"""SQLAlchemy async engine + sessionmaker (PostgreSQL + pgvector)"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from src.config.settings import settings

# 构建 async 数据库 URL
# DATABASE_URL 格式：postgresql://trip:trip123@localhost:5432/trip_db
# SQLAlchemy async 需要：postgresql+asyncpg://trip:trip123@localhost:5432/trip_db
db_url = settings.database_url
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    db_url,
    echo=settings.node_env == "development",
    pool_size=10,
    max_overflow=20,
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """初始化数据库连接 + 确保扩展已启用 + 装慢查询日志 hook"""
    async with engine.begin() as conn:
        # 确保 pgvector 扩展已启用（幂等操作）
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # 验证连接
        await conn.execute(text("SELECT 1"))

    # 慢查询日志 hook（threshold 100ms）
    from src.utils.sql_logger import attach_slow_query_log
    attach_slow_query_log(engine.sync_engine, threshold_ms=100)


async def close_db():
    """关闭数据库连接池"""
    await engine.dispose()


async def get_db() -> AsyncSession:
    """FastAPI dependency：获取数据库 session"""
    async with async_session() as session:
        yield session
