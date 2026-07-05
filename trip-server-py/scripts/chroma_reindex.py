"""
从 MySQL 批量重索引 ChromaDB（Python 版）。

读取 spots 表数据，通过 bge-small-zh 生成 embedding 后写入 ChromaDB。
支持增量索引（跳过已有 vector_id 的记录）。

用法: uv run python scripts/chroma_reindex.py
       uv run python scripts/chroma_reindex.py --force   # 全量重索引
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("chroma-reindex")

BATCH = 100


def _build_document(spot: dict) -> str:
    """构建用于 embedding 的文档文本（与 knowledge_service 保持一致）"""
    tags = " ".join(spot.get("tags", [])) if isinstance(spot.get("tags"), list) else str(spot.get("tags", ""))
    return f"{spot['city']} {spot['name']} {spot['description']} {tags} {spot['category']}"


async def main():
    parser = argparse.ArgumentParser(description="ChromaDB 重索引")
    parser.add_argument("--force", action="store_true", help="全量重索引（忽略已有 vector_id）")
    args = parser.parse_args()

    print("=== Chroma 重索引 ===\n")

    # ── 连接 ChromaDB ──
    chroma_url = settings.chroma_url or "http://localhost:8000"
    logger.info("连接 ChromaDB: %s", chroma_url)
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    if "://" in chroma_url:
        protocol, rest = chroma_url.split("://", 1)
    else:
        protocol, rest = "http", chroma_url
    if ":" in rest:
        host, port_str = rest.split(":", 1)
        port = int(port_str)
    else:
        host = rest
        port = 8001

    client = chromadb.HttpClient(
        host=host,
        port=port,
        settings=ChromaSettings(allow_reset=False, anonymized_telemetry=False),
    )

    try:
        collection = client.get_collection(name="spots")
        existing_count = collection.count()
        logger.info("Chroma 现有集合: spots (%d 条)", existing_count)
    except Exception:
        logger.info("集合 'spots' 不存在，创建新集合")
        collection = client.create_collection(
            name="spots",
            metadata={"hnsw:space": "cosine"},
        )
        existing_count = 0

    # 获取已存在的 vector_id
    existing_ids: set[str] = set()
    if not args.force and existing_count > 0:
        existing_data = collection.get()
        existing_ids = set(existing_data.get("ids") or [])
        logger.info("Chroma 现有 vector_id: %d", len(existing_ids))

    # ── 从 MySQL 读取 spots ──
    db_url = settings.database_url
    if db_url.startswith("mysql://"):
        db_url = db_url.replace("mysql://", "mysql+asyncmy://", 1)

    engine = create_async_engine(db_url)
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        if args.force or not existing_ids:
            result = await session.execute(
                select(sql_text("*")).select_from(sql_text("spots")).order_by(sql_text("id"))
            )
        else:
            result = await session.execute(
                sql_text(
                    "SELECT * FROM spots WHERE vector_id IS NULL OR vector_id NOT IN :ids ORDER BY id"
                ),
                {"ids": tuple(existing_ids) if existing_ids else ("",)},
            )
        spots = result.mappings().all()

    await engine.dispose()
    logger.info("需写入: %d 条\n", len(spots))

    if not spots:
        logger.info("无需写入，ChromaDB 已是最新")
        return

    # ── 逐批写入 ChromaDB ──
    from src.services.rag.embeddings import embed_documents

    done = 0
    for i in range(0, len(spots), BATCH):
        batch = spots[i : i + BATCH]
        texts = [_build_document(dict(s)) for s in batch]
        embeddings = await asyncio.to_thread(embed_documents, texts)

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict] = []

        for j, s in enumerate(batch):
            s_dict = dict(s)
            spot_id = s_dict["id"]
            # 使用现有的 vector_id 或基于 id 生成
            vid = s_dict.get("vector_id") or f"spot-{spot_id}"
            ids.append(vid)
            documents.append(
                f"{s_dict['city']} {s_dict['name']} {s_dict['description']} "
                f"{json.dumps(s_dict.get('tags', []), ensure_ascii=False)}"
            )
            metadatas.append({
                "city": s_dict.get("city", ""),
                "name": s_dict.get("name", ""),
                "category": s_dict.get("category", ""),
                "tags": json.dumps(s_dict.get("tags", []), ensure_ascii=False),
                "rating": s_dict.get("rating") or 0,
            })

        collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        done += len(batch)
        logger.info("  %d/%d", done, len(spots))

    final_count = collection.count()
    logger.info("\nChroma 总数: %d", final_count)
    logger.info("完成")


if __name__ == "__main__":
    asyncio.run(main())
