"""arq worker 任务 —— 异步把 Spot 同步到 ChromaDB 向量库。

改造动机（决策文档 §3.1）：
- 原 knowledge_service.create_spot / update_spot / bulk_import_spots 都同步等待
  embedding 生成 + Chroma 写入，API P95 高达 800ms+。
- 改为入队：API commit MySQL 后立即返回，< 5ms 入队，worker 异步消费。

设计要点：
- 用 Chroma 的 upsert 替代「先 delete 再 add」——upsert 是 atomic 操作，
  避免 update 路径上"先 delete 成功但 add 失败"导致的
  "spot 在 MySQL 但 Chroma 找不到"状态。
- worker 函数接受 vector_id + doc_text + metadata 入参，**不依赖 MySQL 读取**，
  这样 spot 即使被删除，任务也不会失败（最多是"向量冗余"），保证可靠投递。
- ctx 默认为 None：arq 端自动注入（dict），降级路径传 fake_ctx。
- 失败重试：arq max_tries=3 指数退避（worker.py 配置）。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def sync_spot_to_chroma(
    ctx: Optional[dict],
    vector_id: str,
    doc_text: str,
    metadata: dict[str, Any],
    spot_id: Optional[int] = None,
) -> dict:
    """把 Spot 同步到 ChromaDB spots 集合（upsert 语义）。

    适用场景：create / update / bulk_import 三种入口统一走这个任务。
    失败抛错会被 arq 重试（worker.py 配置 max_tries=3 指数退避）。

    Args:
        ctx: arq 注入的上下文（含 job_id / job_try 等）；降级路径为 None 时构造 fake ctx
        vector_id: MySQL spot.vector_id（Chroma 主键，必填）
        doc_text: embedding 文档文本（与 build_embedding_document 输出一致）
        metadata: Chroma 元数据（city/name/category/tags/rating）
        spot_id: MySQL spot.id（仅用于日志/可观测性，可选；bulk_import 时可能尚未分配）

    Returns:
        {"spot_id": int | None, "vector_id": str, "status": "synced", "attempt": int}

    Raises:
        RuntimeError: Chroma 不可用（5s 超时 / 冷却期内），arq 会自动重试
    """
    # 兼容降级路径：ctx 为 None 时构造 fake ctx
    if ctx is None:
        ctx = {"job_id": None, "job_try": 1, "degraded": True}

    # 懒导入：避免模块 import-time 把整个 chroma / embeddings 链路拉起来
    from src.services.rag.embeddings import embed_query_async
    from src.services.rag.chroma_client import get_spots_collection, run_sync

    # 1. 生成 embedding（BGE 模型，可能 1-3s）
    embedding = await embed_query_async(doc_text)
    logger.debug(
        "[sync_spot_to_chroma] embedding done spot_id=%s dim=%d",
        spot_id, len(embedding),
    )

    # 2. 拿 spots 集合（带 5s 超时 + 60s 冷却期快速失败）
    collection = await get_spots_collection()

    # 3. upsert 到 Chroma
    #    用 upsert 而非"先 delete 再 add"——atomic 语义，避免中间态不一致。
    #    id 已存在 → 更新；不存在 → 新建。两种入口（create / update）都覆盖。
    await run_sync(
        collection.upsert,
        ids=[vector_id],
        embeddings=[embedding],
        documents=[doc_text],
        metadatas=[metadata],
    )

    attempt = ctx.get("job_try", 1)
    logger.info(
        "[sync_spot_to_chroma] ok spot_id=%s vector_id=%s attempt=%s",
        spot_id, vector_id, attempt,
    )
    return {
        "spot_id": spot_id,
        "vector_id": vector_id,
        "status": "synced",
        "attempt": attempt,
    }


# ---------------------------------------------------------------------------
# 高层 helper：把 spot → chroma 的入队样板代码封一层
# ---------------------------------------------------------------------------
# 决策文档 review P1-2：knowledge_service 3 处入队代码结构重复（build_embedding_document +
# metadata 构造 + get_task_queue().enqueue + job_id 拼装），抽出来统一封装。
# 业务方调用 1 行即可，无需关心 job_id 格式 / arq pool 是否注入 / 降级路径。


async def enqueue_spot_chroma_sync(
    *,
    spot_id: int,
    vector_id: str,
    city: str,
    name: str,
    description: Optional[str],
    tags: Any,
    category: Optional[str],
    rating: Optional[float],
    job_kind: str,  # "create" / "update"
) -> Optional[str]:
    """单 spot → chroma 入队（create / update 路径）。

    失败静默降级（task_queue.enqueue 内部已处理）——MySQL 数据已落库，
    chroma 同步失败不影响 API 返回。脏数据修复：scripts/chroma_reindex.py --force。

    Returns:
        成功入队返回 job_id（str）；失败/降级返回 None
    """
    from src.services.task_queue import get_task_queue

    import json
    from src.services.knowledge_service import build_embedding_document  # type: ignore

    doc_text = build_embedding_document({
        "city": city,
        "name": name,
        "description": description,
        "tags": tags,
        "category": category,
    })
    metadata = {
        "city": city,
        "name": name,
        "category": category,
        # Chroma metadata 要求基本类型，tags 是 list 时序列化为 JSON 字符串
        "tags": tags if isinstance(tags, str) else json.dumps(tags, ensure_ascii=False),
        "rating": rating or 0,
    }
    return await get_task_queue().enqueue(
        sync_spot_to_chroma,
        spot_id=spot_id,
        vector_id=vector_id,
        doc_text=doc_text,
        metadata=metadata,
        job_id=f"chroma_sync:{job_kind}:{spot_id}",
    )


async def enqueue_bulk_chroma_sync(
    *,
    vector_ids: list[str],
    doc_texts: list[str],
    metadatas: list[dict],
) -> list[Optional[str]]:
    """批量入队（bulk 路径，spot_id 不可用，用 vector_id 作幂等键）。

    用 asyncio.gather 并发入队（N 个 job 一次 round-trip），失败单独重试。

    Returns:
        每个 job 的入队结果（job_id 或 None），顺序与入参对应
    """
    from src.services.task_queue import get_task_queue
    import asyncio

    tq = get_task_queue()
    return await asyncio.gather(*[
        tq.enqueue(
            sync_spot_to_chroma,
            vector_id=vector_ids[i],
            doc_text=doc_texts[i],
            metadata=metadatas[i],
            # spot_id 留 None（commit 后才能拿到；用 vector_id 作幂等键足够）
            job_id=f"chroma_sync:bulk:{vector_ids[i]}",
        )
        for i in range(len(vector_ids))
    ])
