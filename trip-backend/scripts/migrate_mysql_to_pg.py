"""
MySQL -> PostgreSQL 数据迁移脚本。

从 MySQL 读取所有表数据，按外键依赖顺序写入 PostgreSQL。
迁移完成后对 spots / spot_docs 批量计算 embedding。

前置条件：
- MySQL 服务可访问（源库）
- PostgreSQL 服务可访问（目标库，已执行 create_tables.py 建表）
- 已安装 asyncmy（临时用于读取 MySQL）：uv pip install asyncmy

用法: uv run python scripts/migrate_mysql_to_pg.py
       uv run python scripts/migrate_mysql_to_pg.py --skip-embedding  # 跳过 embedding 计算
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, select, MetaData
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("migrate")

# 迁移顺序（外键依赖）
TABLE_ORDER = [
    "roles",
    "users",
    "conversations",
    "messages",
    "trips",
    "spots",
    "spot_docs",
    "feedbacks",
    "agent_steps",
    "token_usage_logs",
    "password_resets",
]

# 需要从源数据中移除的列（PG 新增的，MySQL 中没有）
PG_ONLY_COLUMNS = {
    "spots": ["embedding"],
    "spot_docs": ["embedding"],
}

# MySQL 中有但 PG 中已移除的列
MYSQL_ONLY_COLUMNS = {
    "spots": ["vector_id"],
    "spot_docs": ["embedding_id"],
}

# MySQL 用 tinyint(1) 存布尔，PG 需要真正的 bool
BOOLEAN_COLUMNS = {
    "conversations": ["summary_error"],
    "messages": ["excluded_from_context"],
    "password_resets": ["used"],
}

BATCH_SIZE = 500


async def migrate_table(
    mysql_session: AsyncSession,
    pg_session: AsyncSession,
    table_name: str,
) -> int:
    """迁移单张表，返回迁移行数。"""
    # 1. 从 MySQL 读取全部数据
    result = await mysql_session.execute(text(f"SELECT * FROM `{table_name}`"))
    rows = result.mappings().all()

    if not rows:
        logger.info("  %s: 0 行（空表）", table_name)
        return 0

    # 2. 过滤列 + 布尔类型转换
    skip_cols = set(MYSQL_ONLY_COLUMNS.get(table_name, []))
    bool_cols = set(BOOLEAN_COLUMNS.get(table_name, []))
    cleaned_rows = []
    for row in rows:
        cleaned = {}
        for k, v in row.items():
            if k in skip_cols:
                continue
            if k in bool_cols:
                cleaned[k] = bool(v) if v is not None else None
            else:
                cleaned[k] = v
        cleaned_rows.append(cleaned)

    # 3. 批量写入 PG
    if not cleaned_rows:
        return 0

    columns = list(cleaned_rows[0].keys())
    col_str = ", ".join(f'"{c}"' for c in columns)
    val_str = ", ".join(f":{c}" for c in columns)
    insert_sql = text(f'INSERT INTO "{table_name}" ({col_str}) VALUES ({val_str})')

    count = 0
    for i in range(0, len(cleaned_rows), BATCH_SIZE):
        batch = cleaned_rows[i: i + BATCH_SIZE]
        await pg_session.execute(insert_sql, batch)
        count += len(batch)

    await pg_session.commit()
    logger.info("  %s: %d 行", table_name, count)
    return count


async def compute_embeddings(pg_engine):
    """批量计算 spots 和 spot_docs 的 embedding。"""
    from src.models.spot import Spot
    from src.models.spot_doc import SpotDoc
    from src.services.rag.embeddings import embed_documents
    from sqlalchemy import update

    SessionLocal = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    # spots embedding
    async with SessionLocal() as session:
        result = await session.execute(
            select(Spot).where(Spot.embedding.is_(None)).order_by(Spot.id)
        )
        spots = result.scalars().all()

    logger.info("需计算 embedding: spots=%d", len(spots))

    if spots:
        batch_size = 64
        async with SessionLocal() as session:
            for i in range(0, len(spots), batch_size):
                batch = spots[i: i + batch_size]
                texts_list = []
                for s in batch:
                    tags = " ".join(s.tags) if isinstance(s.tags, list) else ""
                    texts_list.append(f"{s.city} {s.name} {s.description} {tags} {s.category}")
                embeddings = await asyncio.to_thread(embed_documents, texts_list)
                for spot, emb in zip(batch, embeddings):
                    await session.execute(
                        update(Spot).where(Spot.id == spot.id).values(embedding=emb)
                    )
                await session.commit()
                logger.info("  spots embedding: %d/%d", min(i + batch_size, len(spots)), len(spots))

    # spot_docs embedding
    async with SessionLocal() as session:
        result = await session.execute(
            select(SpotDoc).where(SpotDoc.embedding.is_(None)).order_by(SpotDoc.id)
        )
        docs = result.scalars().all()

    logger.info("需计算 embedding: spot_docs=%d", len(docs))

    if docs:
        batch_size = 64
        async with SessionLocal() as session:
            for i in range(0, len(docs), batch_size):
                batch = docs[i: i + batch_size]
                texts_list = [d.content for d in batch]
                embeddings = await asyncio.to_thread(embed_documents, texts_list)
                for doc, emb in zip(batch, embeddings):
                    await session.execute(
                        update(SpotDoc).where(SpotDoc.id == doc.id).values(embedding=emb)
                    )
                await session.commit()
                logger.info("  spot_docs embedding: %d/%d", min(i + batch_size, len(docs)), len(docs))


async def main():
    parser = argparse.ArgumentParser(description="MySQL -> PostgreSQL 数据迁移")
    parser.add_argument("--mysql-url", help="MySQL 连接 URL（默认从 .env 读取旧配置）")
    parser.add_argument("--skip-embedding", action="store_true", help="跳过 embedding 计算")
    args = parser.parse_args()

    # MySQL 源库 URL
    mysql_url = args.mysql_url or "mysql+asyncmy://root:root@localhost:3306/trip_db"

    # PG 目标库 URL
    pg_url = settings.database_url
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    print("=== MySQL -> PostgreSQL 数据迁移 ===")
    print(f"源库: {mysql_url.split('@')[1] if '@' in mysql_url else mysql_url}")
    print(f"目标: {pg_url.split('@')[1] if '@' in pg_url else pg_url}")
    print()

    mysql_engine = create_async_engine(mysql_url)
    pg_engine = create_async_engine(pg_url)

    MysqlSession = sessionmaker(mysql_engine, class_=AsyncSession, expire_on_commit=False)
    PgSession = sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)

    total = 0
    async with MysqlSession() as mysql_session, PgSession() as pg_session:
        # 确保 PG 扩展已启用
        await pg_session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await pg_session.commit()

        for table_name in TABLE_ORDER:
            try:
                count = await migrate_table(mysql_session, pg_session, table_name)
                total += count
            except Exception as e:
                logger.error("  %s 迁移失败: %s", table_name, e)
                await pg_session.rollback()

    print(f"\n数据迁移完成，共 {total} 行")

    # 重置序列（PG 自增 ID 需要从最大值开始）
    async with PgSession() as pg_session:
        for table_name in TABLE_ORDER:
            try:
                await pg_session.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM \"{table_name}\"), 0) + 1, false)"
                ))
            except Exception:
                pass
        await pg_session.commit()
    print("序列重置完成")

    # 计算 embedding
    if not args.skip_embedding:
        print("\n开始计算 embedding...")
        await compute_embeddings(pg_engine)
        print("embedding 计算完成")
    else:
        print("\n跳过 embedding 计算（--skip-embedding）")
        print("后续可执行: uv run python scripts/pgvector_reindex.py")

    await mysql_engine.dispose()
    await pg_engine.dispose()
    print("\n迁移全部完成")


if __name__ == "__main__":
    asyncio.run(main())
