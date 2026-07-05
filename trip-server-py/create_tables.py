"""数据库迁移脚本 - 创建缺失的表"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from src.config.settings import settings
from src.models.base import Base

# 导入所有模型，确保它们在 Base.metadata 中注册
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.trip import Trip
from src.models.spot import Spot
from src.models.agent_step import AgentStep
from src.models.feedback import Feedback
from src.models.token_usage_log import TokenUsageLog


async def create_tables():
    """创建缺失的数据库表"""
    print("开始创建缺失的表...")
    
    # 构建 async 数据库 URL（与 database.py 相同的逻辑）
    db_url = settings.database_url
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)
    
    # 使用异步引擎
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 确保 FULLTEXT 索引存在（SQLAlchemy 自动创建可能不生效）
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE FULLTEXT INDEX IF NOT EXISTS ft_name_desc "
                "ON spots (name, description)"
            ))
    except Exception:
        pass  # 索引已存在或 MySQL 版本不支持 IF NOT EXISTS 时忽略

    print("✓ 表创建完成")
    print("\n已创建的表:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")

    await engine.dispose()


if __name__ == "__main__":
    import asyncio
    asyncio.run(create_tables())
