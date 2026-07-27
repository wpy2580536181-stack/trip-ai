"""M3-A 阶段测试 —— fetch_city_wiki worker 任务的端到端验证。

覆盖 4 类：
1. fetch_city_wiki worker 函数本身：mock fetch_city + Spot 查询，验证写文件 + return dict
2. from_db 模式：mock Spot 查表返该城所有 spots
3. snapshot 模式：mock SPOTS_DIR 快照读
4. 边界场景：spot 表为空、fetch_city 返空列表、ctx=None
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 测试 1：from_db=True 模式
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_city_wiki_from_db_writes_file():
    """worker 函数（from_db=True）：从 Spot 查 spots → 调 fetch_city → 写文件。

    Mock 掉 fetch_city 直接返 mock results，验证：
    1. 写文件路径正确（wiki_raw/{city}.json）
    2. 文件内容跟 fetch_city return 一致
    3. return dict 字段正确
    """
    from sqlalchemy import select
    from src.models.spot import Spot

    # mock Spot 查询返 3 个景点
    mock_rows = [
        ("故宫",), ("天坛",), ("颐和园",),
    ]

    # mock fetch_city 返 2 个 results
    mock_results = [
        {
            "spot_name": "故宫",
            "city": "北京",
            "title": "故宫",
            "extract": "北京故宫...",
            "pageid": 1,
            "source_url": "https://zh.wikipedia.org/wiki/故宫",
            "lang": "zh",
        },
        {
            "spot_name": "天坛",
            "city": "北京",
            "title": "天坛",
            "extract": "天坛...",
            "pageid": 2,
            "source_url": "https://zh.wikipedia.org/wiki/天坛",
            "lang": "zh",
        },
    ]

    # 临时 wiki_raw dir
    with tempfile.TemporaryDirectory() as tmp_wiki_raw:
        with patch("src.config.database.async_session") as mock_async_session, \
             patch("scripts.fetch_wiki.fetch_city",
                   AsyncMock(return_value=mock_results)) as mock_fetch_city, \
             patch("scripts.fetch_wiki.WIKI_RAW_DIR", tmp_wiki_raw):
            # 构造 mock session：execute return mock_rows
            mock_session = MagicMock()
            mock_result = MagicMock()
            mock_result.all = MagicMock(return_value=mock_rows)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_async_session.return_value = mock_session

            from src.services.tasks.wiki_fetch import fetch_city_wiki

            ctx = {"job_id": "test-job-1", "job_try": 1}
            result = await fetch_city_wiki(
                ctx, city="北京", from_db=True, concurrency=4,
            )

        # 1. fetch_city 被调，参数正确
        mock_fetch_city.assert_awaited_once()
        kwargs = mock_fetch_city.call_args.kwargs
        assert kwargs["city"] == "北京"
        assert len(kwargs["spots"]) == 3
        assert kwargs["concurrency"] == 4

        # 2. 写文件路径正确
        expected_path = os.path.join(tmp_wiki_raw, "北京.json")
        assert result["written_to"] == expected_path
        assert os.path.exists(expected_path)

        # 3. 文件内容跟 fetch_city return 一致
        with open(expected_path, "r", encoding="utf-8") as fh:
            written = json.load(fh)
        assert written == mock_results

        # 4. return dict 字段正确
        assert result["city"] == "北京"
        assert result["fetched"] == 2
        assert result["source"] == "db"
        assert result["total_spots"] == 3
        assert result["attempt"] == 1


# ---------------------------------------------------------------------------
# 测试 2：from_db=False 模式（snapshot）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_city_wiki_from_snapshot_writes_file():
    """worker 函数（from_db=False）：从 SPOTS_DIR 快照读 spots → 写文件。"""
    mock_results = [
        {
            "spot_name": "西湖",
            "city": "杭州",
            "title": "西湖",
            "extract": "杭州西湖...",
            "pageid": 100,
            "source_url": "https://zh.wikipedia.org/wiki/西湖",
            "lang": "zh",
        },
    ]

    with tempfile.TemporaryDirectory() as tmp_spots, \
         tempfile.TemporaryDirectory() as tmp_wiki_raw:
        # 写一个 snapshot 文件
        snapshot_path = os.path.join(tmp_spots, "杭州.json")
        with open(snapshot_path, "w", encoding="utf-8") as fh:
            json.dump([
                {"name": "西湖", "city": "杭州"},
                {"name": "灵隐寺", "city": "杭州"},
            ], fh)

        with patch("scripts.fetch_wiki.fetch_city",
                   AsyncMock(return_value=mock_results)) as mock_fetch_city, \
             patch("scripts.fetch_wiki.SPOTS_DIR", tmp_spots), \
             patch("scripts.fetch_wiki.WIKI_RAW_DIR", tmp_wiki_raw):
            from src.services.tasks.wiki_fetch import fetch_city_wiki

            ctx = {"job_id": "test-job-2", "job_try": 1}
            result = await fetch_city_wiki(
                ctx, city="杭州", from_db=False,
            )

        mock_fetch_city.assert_awaited_once()
        assert result["source"] == "snapshot"
        assert result["fetched"] == 1
        assert result["total_spots"] == 2
        assert result["written_to"] == os.path.join(tmp_wiki_raw, "杭州.json")


# ---------------------------------------------------------------------------
# 测试 3：spot 表为空时跳过
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_city_wiki_no_spots_returns_skipped():
    """从 PG 查 0 个 spots → 返 skipped_reason="no_spots"，不调 fetch_city。"""
    with patch("src.config.database.async_session") as mock_async_session:
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[])
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.wiki_fetch import fetch_city_wiki

        ctx = {"job_id": "test-job-3", "job_try": 1}
        result = await fetch_city_wiki(
            ctx, city="不存在的城市", from_db=True,
        )

    assert result["fetched"] == 0
    assert result["total_spots"] == 0
    assert result["skipped_reason"] == "no_spots"
    assert result["written_to"] is None


# ---------------------------------------------------------------------------
# 测试 4：fetch_city 返空列表不写文件
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_city_wiki_empty_results_no_file():
    """fetch_city 返空列表（维基无词条）→ 不写文件，fetched=0。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("scripts.fetch_wiki.fetch_city",
               AsyncMock(return_value=[])) as mock_fetch_city:
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[("故宫",)])
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.wiki_fetch import fetch_city_wiki

        ctx = {"job_id": "test-job-4", "job_try": 1}
        result = await fetch_city_wiki(
            ctx, city="北京", from_db=True,
        )

    assert result["fetched"] == 0
    assert result["total_spots"] == 1
    assert result["written_to"] is None


# ---------------------------------------------------------------------------
# 测试 5：ctx=None 降级路径
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_city_wiki_handles_none_ctx():
    """ctx=None（asyncio 降级路径）→ 不崩，attempt 默认为 1。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("scripts.fetch_wiki.fetch_city",
               AsyncMock(return_value=[])):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.all = MagicMock(return_value=[("x",)])
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.wiki_fetch import fetch_city_wiki

        result = await fetch_city_wiki(
            None, city="x", from_db=True,
        )
        assert result["attempt"] == 1
