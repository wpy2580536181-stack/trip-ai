"""arq worker 任务 —— 异步计算 Spot embedding 并写入 PostgreSQL pgvector 列。

替代原 chroma_sync.py（已删除），不再需要独立的向量数据库，
embedding 直接存储在 spots.embedding / spot_docs.embedding 列中。

设计要点：
- worker 函数接受 spot_id + 文本字段入参，计算 embedding 后 UPDATE 回 PG。
- 失败重试：arq max_tries=3 指数退避（worker.py 配置）。
- 降级路径：Redis 不可用时走 asyncio.create_task 内存模式。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def sync_spot_embedding(
    ctx: Optional[dict],
    spot_id: int,
    city: str,
    name: str,
    description: str,
    tags: Any = None,
    category: str = "",
) -> dict:
    """计算 Spot embedding 并写入 PG spots.embedding 列。

    适用场景：create / update 两种入口统一走这个任务。
    """
    from src.services.rag.embeddings import embed_query_async
    from src.config.database import async_session
    from src.models.spot import Spot
    from sqlalchemy import update

    # 构建 embedding 文档
    tags_str = " ".join(tags) if isinstance(tags, list) else ""
    doc_text = f"{city} {name} {description} {tags_str} {category}"

    # 计算向量
    embedding = await embed_query_async(doc_text)

    # 写入 PG
    async with async_session() as db:
        stmt = (
            update(Spot)
            .where(Spot.id == spot_id)
            .values(embedding=embedding)
        )
        await db.execute(stmt)
        await db.commit()

    logger.info("Spot embedding 已更新", spot_id=spot_id, name=name)
    return {"spot_id": spot_id, "status": "ok"}


async def sync_spot_doc_embedding(
    ctx: Optional[dict],
    doc_id: int,
    content: str,
) -> dict:
    """计算 SpotDoc embedding 并写入 PG spot_docs.embedding 列。"""
    from src.services.rag.embeddings import embed_query_async
    from src.config.database import async_session
    from src.models.spot_doc import SpotDoc
    from sqlalchemy import update

    embedding = await embed_query_async(content)

    async with async_session() as db:
        stmt = (
            update(SpotDoc)
            .where(SpotDoc.id == doc_id)
            .values(embedding=embedding)
        )
        await db.execute(stmt)
        await db.commit()

    logger.info("SpotDoc embedding 已更新", doc_id=doc_id)
    return {"doc_id": doc_id, "status": "ok"}


async def enqueue_embedding_sync(
    *,
    spot_id: int,
    city: str,
    name: str,
    description: str,
    tags: Any = None,
    category: str = "",
    job_kind: str = "create",
) -> Optional[str]:
    """入队单个 spot embedding 计算任务。"""
    from src.services.task_queue import get_task_queue

    return await get_task_queue().enqueue(
        sync_spot_embedding,
        spot_id=spot_id,
        city=city,
        name=name,
        description=description,
        tags=tags,
        category=category,
        job_id=f"embedding_sync:{job_kind}:{spot_id}",
    )


async def enqueue_bulk_embedding_sync(
    spots: List[Dict[str, Any]],
) -> List[Optional[str]]:
    """批量入队 spot embedding 计算任务。

    Args:
        spots: [{"spot_id": int, "city": str, "name": str, "description": str, "tags": ..., "category": str}, ...]

    Returns:
        每个 job 的入队结果（job_id 或 None）
    """
    import asyncio
    from src.services.task_queue import get_task_queue

    tq = get_task_queue()
    return list(await asyncio.gather(*[
        tq.enqueue(
            sync_spot_embedding,
            spot_id=s["spot_id"],
            city=s.get("city", ""),
            name=s.get("name", ""),
            description=s.get("description", ""),
            tags=s.get("tags"),
            category=s.get("category", ""),
            job_id=f"embedding_sync:bulk:{s['spot_id']}",
        )
        for s in spots
    ], return_exceptions=True))
