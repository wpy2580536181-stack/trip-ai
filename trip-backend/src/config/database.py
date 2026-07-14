"""SQLAlchemy async engine + sessionmaker"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from src.config.settings import settings

# 构建 async 数据库 URL
# DATABASE_URL 格式：mysql://root:root@localhost:3306/trip_db
# SQLAlchemy async 需要：mysql+asyncmy://root:root@localhost:3306/trip_db
db_url = settings.database_url
if db_url.startswith("mysql://"):
    db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)

engine = create_async_engine(
    db_url,
    echo=settings.node_env == "development",
    pool_size=10,
    max_overflow=20,
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """初始化数据库连接（创建连接池）"""
    # SQLAlchemy 连接池是懒加载的，这里执行一个简单的查询来验证连接
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db():
    """关闭数据库连接池"""
    await engine.dispose()


async def get_db() -> AsyncSession:
    """FastAPI dependency：获取数据库 session"""
    async with async_session() as session:
        yield session
