"""M1 阶段测试 —— arq 改造的端到端验证。

覆盖 4 类：
1. chroma_sync worker 函数本身：mock chroma + embeddings，验证 upsert 被正确调用
2. knowledge_service.create_spot 改造后：mock task_queue，验证入队被调用（不再直接 await embedding）
3. knowledge_service.update_spot 改造后：同上
4. knowledge_service.bulk_import_spots 改造后：每 spot 入队一次
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 测试 1：chroma_sync worker 函数
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sync_spot_to_chroma_calls_upsert_with_correct_args():
    """worker 函数：调 embed_query_async → get_spots_collection → collection.upsert。

    Mock 掉所有外部依赖（embedding / chroma），验证参数透传正确。
    """
    # 准备 mock
    fake_embedding = [0.1] * 512  # BGE 512 维
    mock_collection = MagicMock()
    mock_collection.upsert = MagicMock()  # run_sync 把它丢到线程池

    with patch("src.services.rag.embeddings.embed_query_async",
               AsyncMock(return_value=fake_embedding)) as mock_embed, \
         patch("src.services.rag.chroma_client.get_spots_collection",
               AsyncMock(return_value=mock_collection)) as mock_get_col, \
         patch("src.services.rag.chroma_client.run_sync",
               AsyncMock(return_value=None)) as mock_run_sync:
        from src.services.tasks.chroma_sync import sync_spot_to_chroma

        ctx = {"job_id": "test-job-1", "job_try": 1}
        metadata = {
            "city": "Beijing",
            "name": "故宫",
            "category": "历史",
            "tags": '["历史", "古建筑"]',  # JSON 字符串
            "rating": 5,
        }

        result = await sync_spot_to_chroma(
            ctx=ctx,
            spot_id=42,
            vector_id="vector-abc-123",
            doc_text="北京 故宫 A new spot",
            metadata=metadata,
        )

    # 1. embed_query_async 被调用，参数是 doc_text
    mock_embed.assert_awaited_once_with("北京 故宫 A new spot")
    # 2. get_spots_collection 被调用
    mock_get_col.assert_awaited_once()
    # 3. run_sync 收到 collection.upsert + 正确参数（atomic 语义，单次调用搞定）
    mock_run_sync.assert_awaited_once()
    args, kwargs = mock_run_sync.call_args
    # run_sync(fn, **kwargs) → fn=collection.upsert，upsert 的所有参数走 kwargs
    assert args[0] == mock_collection.upsert
    assert kwargs["ids"] == ["vector-abc-123"]
    assert kwargs["embeddings"] == [fake_embedding]
    assert kwargs["documents"] == ["北京 故宫 A new spot"]
    assert kwargs["metadatas"] == [metadata]
    # 4. 返回值正确
    assert result == {
        "spot_id": 42,
        "vector_id": "vector-abc-123",
        "status": "synced",
        "attempt": 1,
    }


@pytest.mark.asyncio
async def test_sync_spot_to_chroma_accepts_none_ctx_for_degraded_path():
    """降级路径传 ctx=None → worker 内部构造 fake ctx。"""
    fake_embedding = [0.1] * 512
    mock_collection = MagicMock()
    mock_collection.upsert = MagicMock()

    with patch("src.services.rag.embeddings.embed_query_async",
               AsyncMock(return_value=fake_embedding)), \
         patch("src.services.rag.chroma_client.get_spots_collection",
               AsyncMock(return_value=mock_collection)), \
         patch("src.services.rag.chroma_client.run_sync",
               AsyncMock(return_value=None)):
        from src.services.tasks.chroma_sync import sync_spot_to_chroma

        # ctx=None 模拟降级路径
        result = await sync_spot_to_chroma(
            ctx=None,
            vector_id="v1",
            doc_text="text",
            metadata={"city": "X"},
        )

    assert result["status"] == "synced"
    assert result["attempt"] == 1  # fake ctx 的 job_try
    assert result["spot_id"] is None


@pytest.mark.asyncio
async def test_sync_spot_to_chroma_works_without_spot_id():
    """bulk_import 路径：spot_id=None 也能正常执行（仅日志少一个 id）。"""
    fake_embedding = [0.1] * 512
    mock_collection = MagicMock()

    with patch("src.services.rag.embeddings.embed_query_async",
               AsyncMock(return_value=fake_embedding)), \
         patch("src.services.rag.chroma_client.get_spots_collection",
               AsyncMock(return_value=mock_collection)), \
         patch("src.services.rag.chroma_client.run_sync",
               AsyncMock(return_value=None)):
        from src.services.tasks.chroma_sync import sync_spot_to_chroma

        result = await sync_spot_to_chroma(
            ctx={"job_try": 2},
            vector_id="v1",
            doc_text="text",
            metadata={"city": "X"},
            # spot_id 默认 None
        )

    assert result["spot_id"] is None
    assert result["attempt"] == 2


@pytest.mark.asyncio
async def test_sync_spot_to_chroma_propagates_chroma_failure():
    """Chroma 不可用时抛错 → arq 会捕获并重试。"""
    with patch("src.services.rag.embeddings.embed_query_async",
               AsyncMock(return_value=[0.1] * 512)), \
         patch("src.services.rag.chroma_client.get_spots_collection",
               AsyncMock(side_effect=RuntimeError("Chroma 处于冷却期"))):
        from src.services.tasks.chroma_sync import sync_spot_to_chroma

        with pytest.raises(RuntimeError, match="冷却期"):
            await sync_spot_to_chroma(
                ctx={"job_try": 1},
                vector_id="v1",
                doc_text="text",
                metadata={"city": "X"},
            )


# ---------------------------------------------------------------------------
# 测试 2-4：knowledge_service 改造后——验证入队被调用
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_spot_enqueues_chroma_sync(db_session):
    """create_spot 改造后：MySQL commit 后应入队 sync_spot_to_chroma，不再同步等 embedding。"""
    from src.services.knowledge_service import KnowledgeService
    from src.schemas.knowledge import SpotCreate

    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock(return_value="mock-job-id")

    with patch("src.services.task_queue.get_task_queue",
               return_value=mock_tq) as mock_get_tq:
        spot_data = SpotCreate(
            name="Test Spot",
            city="Shanghai",
            category="Modern",
            description="A test",
            tags=["modern"],
            avg_cost=50.0,
            duration="2h",
            open_time="09:00-18:00",
            rating=4.5,
        )
        result = await KnowledgeService.create_spot(db_session, spot_data)

    # 1. 验证 spot 已落库
    assert result.id is not None
    assert result.vector_id is not None
    # 2. 验证入队被调用（不再同步等 embedding）
    mock_tq.enqueue.assert_awaited_once()
    args, kwargs = mock_tq.enqueue.call_args
    # 入队函数是 sync_spot_to_chroma
    from src.services.tasks.chroma_sync import sync_spot_to_chroma
    assert args[0] is sync_spot_to_chroma
    # 关键参数验证
    assert kwargs["spot_id"] == result.id
    assert kwargs["vector_id"] == result.vector_id
    assert "doc_text" in kwargs
    assert "metadata" in kwargs
    assert kwargs["job_id"] == f"chroma_sync:create:{result.id}"
    # doc_text 至少包含 city + name
    assert "Shanghai" in kwargs["doc_text"]
    assert "Test Spot" in kwargs["doc_text"]


@pytest.mark.asyncio
async def test_update_spot_enqueues_chroma_sync(db_session):
    """update_spot 改造后：commit 后入队 sync_spot_to_chroma（upsert 而非 delete+add）。"""
    from src.services.knowledge_service import KnowledgeService
    from src.schemas.knowledge import SpotUpdate
    from src.models.spot import Spot

    # 先建一个 spot
    spot = Spot(
        name="Old",
        city="Beijing",
        category="Historical",
        description="Old",
        tags=["history"],
        avg_cost=100.0,
        duration="3h",
        open_time="08:00-17:00",
        rating=4.5,
        vector_id="existing-vector-id",
    )
    db_session.add(spot)
    await db_session.commit()
    await db_session.refresh(spot)

    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock(return_value="mock-job-id")

    with patch("src.services.task_queue.get_task_queue",
               return_value=mock_tq):
        update_data = SpotUpdate(name="New", rating=4.8)
        result = await KnowledgeService.update_spot(db_session, spot.id, update_data)

    # 1. 验证字段已更新
    assert result.name == "New"
    assert result.rating == 4.8
    # 2. 验证入队被调用
    mock_tq.enqueue.assert_awaited_once()
    args, kwargs = mock_tq.enqueue.call_args
    from src.services.tasks.chroma_sync import sync_spot_to_chroma
    assert args[0] is sync_spot_to_chroma
    assert kwargs["vector_id"] == "existing-vector-id"  # 用 spot 现有 vector_id
    assert kwargs["spot_id"] == spot.id
    assert kwargs["job_id"] == f"chroma_sync:update:{spot.id}"


@pytest.mark.asyncio
async def test_update_spot_skips_enqueue_when_no_vector_id(db_session):
    """edge case：spot.vector_id 为空时 update_spot 不应入队（旧 spot 走 seed 路径未分配 vector_id）。"""
    from src.services.knowledge_service import KnowledgeService
    from src.schemas.knowledge import SpotUpdate
    from src.models.spot import Spot

    spot = Spot(
        name="NoVector",
        city="X",
        category="X",
        description="X",
        tags=[],
        avg_cost=0.0,
        duration="1h",
        open_time="00:00-24:00",
        rating=0.0,
        vector_id=None,  # 无 vector_id
    )
    db_session.add(spot)
    await db_session.commit()
    await db_session.refresh(spot)

    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock()

    with patch("src.services.task_queue.get_task_queue",
               return_value=mock_tq):
        await KnowledgeService.update_spot(db_session, spot.id, SpotUpdate(name="Updated"))

    # 不应入队（vector_id 为空）
    mock_tq.enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_import_spots_enqueues_one_job_per_spot(db_session):
    """bulk_import_spots 改造后：每 spot 一 job 入队（细粒度重试）。"""
    from src.services.knowledge_service import KnowledgeService

    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock(return_value="mock-job-id")

    spots_data = [
        {
            "name": f"Spot {i}",
            "city": "Beijing",
            "category": "Test",
            "description": f"Desc {i}",
            "tags": ["t"],
            "avg_cost": 10.0,
            "duration": "1h",
            "open_time": "00:00-24:00",
            "rating": 4.0,
        }
        for i in range(5)
    ]

    with patch("src.services.task_queue.get_task_queue",
               return_value=mock_tq):
        result = await KnowledgeService.bulk_import_spots(db_session, spots_data)

    # 1. 5 个 spot 全部成功
    assert result["success"] == 5
    assert result["failed"] == 0
    # 2. 入队 5 次（每 spot 一次）
    assert mock_tq.enqueue.await_count == 5
    # 3. 验证入参格式（job_id 用 vector_id 作幂等键）
    for call in mock_tq.enqueue.await_args_list:
        args, kwargs = call
        from src.services.tasks.chroma_sync import sync_spot_to_chroma
        assert args[0] is sync_spot_to_chroma
        assert "vector_id" in kwargs
        assert "doc_text" in kwargs
        assert "metadata" in kwargs
        assert kwargs["job_id"].startswith("chroma_sync:bulk:")
        assert "spot_id" not in kwargs  # bulk 路径不传 spot_id（commit 前没拿到）


@pytest.mark.asyncio
async def test_bulk_import_spots_empty_list_no_enqueue(db_session):
    """edge case：空列表 → 不入队。"""
    from src.services.knowledge_service import KnowledgeService

    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock()

    with patch("src.services.task_queue.get_task_queue",
               return_value=mock_tq):
        result = await KnowledgeService.bulk_import_spots(db_session, [])

    assert result == {"success": 0, "failed": 0, "total": 0, "errors": []}
    mock_tq.enqueue.assert_not_awaited()
