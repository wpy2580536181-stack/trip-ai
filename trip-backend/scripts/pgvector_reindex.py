"""
批量计算 spots 表 embedding 并写入 PostgreSQL pgvector 列。

替代原 chroma_reindex.py，不再需要独立的向量数据库。
支持增量（跳过已有 embedding 的记录）和全量（--force）两种模式。

用法: uv run python scripts/pgvector_reindex.py
       uv run python scripts/pgvector_reindex.py --force   # 全量重算
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update, func, text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

# 全量模型导入：确保 SQLAlchemy mapper 能解析所有关系
import src.models.user  # noqa: F401
import src.models.conversation  # noqa: F401
import src.models.message  # noqa: F401
import src.models.trip  # noqa: F401
import src.models.spot  # noqa: F401
import src.models.spot_doc  # noqa: F401
import src.models.password_reset  # noqa: F401
import src.models.role  # noqa: F401
import src.models.feedback  # noqa: F401
import src.models.agent_step  # noqa: F401
import src.models.token_usage_log  # noqa: F401
from src.models.spot import Spot

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("pgvector-reindex")

BATCH = 64


def _build_document(spot) -> str:
    """构建用于 embedding 的文档文本（与 knowledge_service 保持一致）"""
    tags = " ".join(spot.tags) if isinstance(spot.tags, list) else str(spot.tags or "")
    return f"{spot.city} {spot.name} {spot.description} {tags} {spot.category}"


async def main():
    parser = argparse.ArgumentParser(description="pgvector 批量 embedding 重算")
    parser.add_argument("--force", action="store_true", help="全量重算（忽略已有 embedding）")
    args = parser.parse_args()

    print("=== pgvector 批量 embedding 重算 ===\n")

    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        # 确保扩展已启用
        await session.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await session.commit()

        # 查询需要计算 embedding 的 spots
        if args.force:
            query = select(Spot).order_by(Spot.id)
        else:
            query = select(Spot).where(Spot.embedding.is_(None)).order_by(Spot.id)

        result = await session.execute(query)
        spots = result.scalars().all()

    logger.info("需计算 embedding: %d 条\n", len(spots))

    if not spots:
        logger.info("无需计算，所有 spots 已有 embedding")
        await engine.dispose()
        return

    from src.services.rag.embeddings import embed_documents

    done = 0
    async with SessionLocal() as session:
        for i in range(0, len(spots), BATCH):
            batch = spots[i: i + BATCH]
            texts = [_build_document(s) for s in batch]
            embeddings = await asyncio.to_thread(embed_documents, texts)

            for spot, emb in zip(batch, embeddings):
                stmt = (
                    update(Spot)
                    .where(Spot.id == spot.id)
                    .values(embedding=emb)
                )
                await session.execute(stmt)

            await session.commit()
            done += len(batch)
            logger.info("  %d/%d", done, len(spots))

    # 统计
    async with SessionLocal() as session:
        total = await session.scalar(select(func.count()).select_from(Spot))
        with_emb = await session.scalar(
            select(func.count()).select_from(Spot).where(Spot.embedding.isnot(None))
        )

    logger.info("\nspots 总数: %d, 已有 embedding: %d", total, with_emb)
    logger.info("完成")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
