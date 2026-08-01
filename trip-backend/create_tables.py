"""数据库迁移脚本 - 创建表结构（PostgreSQL + pgvector）"""

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
from src.models.spot_doc import SpotDoc
from src.models.agent_step import AgentStep
from src.models.feedback import Feedback


async def create_tables():
    """创建数据库表结构 + pgvector/zhparser 扩展"""
    print("开始创建表结构...")
    
    # 构建 async 数据库 URL
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        # 确保扩展已启用
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        print("✓ pgvector 扩展已启用")
        
        # 创建表结构
        await conn.run_sync(Base.metadata.create_all)
        print("✓ 表结构创建完成")
        
        # 创建 GIN 全文检索索引（函数索引无法通过 SQLAlchemy __table_args__ 定义）
        fts_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_spots_name_desc_fts ON spots USING gin (to_tsvector('chinese', coalesce(name, '') || ' ' || coalesce(description, '')))",
            "CREATE INDEX IF NOT EXISTS idx_spot_docs_content_fts ON spot_docs USING gin (to_tsvector('chinese', coalesce(content, '')))",
        ]
        for idx_sql in fts_indexes:
            try:
                await conn.execute(text(idx_sql))
                print(f"✓ 全文索引已创建")
            except Exception as e:
                print(f"ℹ  全文索引跳过: {e}")
    
    print("\n已创建的表:")
    for table in Base.metadata.sorted_tables:
        print(f"  - {table.name}")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_tables())
