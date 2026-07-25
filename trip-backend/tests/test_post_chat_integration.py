"""M2 阶段测试 —— 对话结束后处理（post_chat_followup）的端到端验证。

覆盖 3 类：
1. post_chat_followup worker 函数本身：mock summary_service，验证 compress + decision 调用
2. trip_service._post_chat_tasks 改造后：mock task_queue，验证入队被调用（不再 asyncio.create_task）
3. 关键决策只在 is_planning=True 时记录
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 测试 1：post_chat_followup worker 函数（正常路径，is_planning=True）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_chat_followup_compress_and_decision_when_planning():
    """worker 函数（is_planning=True）：调 compress_conversation + append_key_decision。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("src.services.summary_service.summary_service.compress_conversation",
               AsyncMock(return_value=None)) as mock_compress, \
         patch("src.services.summary_service.summary_service.append_key_decision",
               AsyncMock(return_value=None)) as mock_decision:

        # async_session() 是 async context manager
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.post_chat import post_chat_followup

        ctx = {"job_id": "test-job-1", "job_try": 1}
        result = await post_chat_followup(
            ctx,
            conversation_id=42,
            user_message="帮我规划 3 天北京行程",
            is_planning=True,
        )

        # 1. compress 被调用，参数正确
        mock_compress.assert_awaited_once()
        args_compress, _ = mock_compress.call_args
        assert args_compress[1] == 42  # conversation_id

        # 2. decision 被调用，参数正确
        mock_decision.assert_awaited_once()
        args_decision, _ = mock_decision.call_args
        assert args_decision[1] == 42  # conversation_id
        assert "用户发起行程规划" in args_decision[2]
        assert "帮我规划 3 天北京行程" in args_decision[2]

        # 3. 返回值正确
        assert result == {
            "conversation_id": 42,
            "compressed": True,
            "decision_recorded": True,
            "decision_skipped": False,
            "attempt": 1,
        }


# ---------------------------------------------------------------------------
# 测试 2：post_chat_followup worker 函数（非规划对话）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_chat_followup_skip_decision_when_not_planning():
    """worker 函数（is_planning=False）：只压缩，不记录决策。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("src.services.summary_service.summary_service.compress_conversation",
               AsyncMock(return_value=None)) as mock_compress, \
         patch("src.services.summary_service.summary_service.append_key_decision",
               AsyncMock(return_value=None)) as mock_decision:

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.post_chat import post_chat_followup

        ctx = {"job_id": "test-job-2", "job_try": 1}
        result = await post_chat_followup(
            ctx,
            conversation_id=43,
            user_message="今天天气怎么样？",
            is_planning=False,
        )

        # 1. compress 被调用
        mock_compress.assert_awaited_once()
        # 2. decision 没被调用
        mock_decision.assert_not_awaited()
        # 3. 返回值正确
        assert result == {
            "conversation_id": 43,
            "compressed": True,
            "decision_recorded": False,
            "decision_skipped": True,
            "attempt": 1,
        }


# ---------------------------------------------------------------------------
# 测试 3：compress 失败时整体抛错（让 arq 触发重试 / 死信）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_chat_followup_compress_failure_raises():
    """compress 抛错时：整体抛错（让 arq 决定重试 / 死信），不静默。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("src.services.summary_service.summary_service.compress_conversation",
               AsyncMock(side_effect=RuntimeError("DB 连接断开"))) as mock_compress, \
         patch("src.services.summary_service.summary_service.append_key_decision",
               AsyncMock(return_value=None)) as mock_decision:

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.post_chat import post_chat_followup

        ctx = {"job_id": "test-job-3", "job_try": 1}
        with pytest.raises(RuntimeError, match="DB 连接断开"):
            await post_chat_followup(
                ctx, conversation_id=44, user_message="任何消息", is_planning=True,
            )

        # decision 没被执行（compress 失败就立即抛错）
        mock_decision.assert_not_awaited()


# ---------------------------------------------------------------------------
# 测试 4：decision 失败时 warn 但不抛（compress 已成功）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_chat_followup_decision_failure_warns_not_raises():
    """decision 抛错时：warn 但不抛（compress 已成功，决策丢失是次要损失）。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("src.services.summary_service.summary_service.compress_conversation",
               AsyncMock(return_value=None)) as mock_compress, \
         patch("src.services.summary_service.summary_service.append_key_decision",
               AsyncMock(side_effect=ValueError("decision 表字段超长"))) as mock_decision:

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.post_chat import post_chat_followup

        ctx = {"job_id": "test-job-4", "job_try": 1}
        # 不抛错
        result = await post_chat_followup(
            ctx, conversation_id=45, user_message="行程规划", is_planning=True,
        )

        # compress 成功 + decision 失败 → decision_recorded=False
        assert result["compressed"] is True
        assert result["decision_recorded"] is False
        assert result["decision_skipped"] is False


# ---------------------------------------------------------------------------
# 测试 5：降级路径 ctx=None 时不崩
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_chat_followup_handles_none_ctx():
    """ctx=None 时（asyncio 降级路径传入 fake_ctx 前），不崩，attempt 默认为 1。"""
    with patch("src.config.database.async_session") as mock_async_session, \
         patch("src.services.summary_service.summary_service.compress_conversation",
               AsyncMock(return_value=None)) as mock_compress, \
         patch("src.services.summary_service.summary_service.append_key_decision",
               AsyncMock(return_value=None)):

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_async_session.return_value = mock_session

        from src.services.tasks.post_chat import post_chat_followup

        # ctx=None（降级路径）
        result = await post_chat_followup(
            None, conversation_id=46, user_message="x", is_planning=False,
        )
        assert result["attempt"] == 1


# ---------------------------------------------------------------------------
# 测试 6：trip_service._post_chat_tasks 改造后入队被调用
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trip_service_post_chat_tasks_enqueues_job():
    """_post_chat_tasks 改造后：调 task_queue.enqueue 而不是 asyncio.create_task。

    关键验证点：
    1. enqueue 被调用 1 次
    2. 传入 func=post_chat_followup
    3. job_id 格式正确：`post_chat:followup:{conversation_id}`（幂等键）
    4. is_planning 在 API 端预计算（不是 worker 内 import router）
    """
    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock(return_value="fake-job-id")

    with patch("src.services.task_queue.get_task_queue", return_value=mock_tq):
        from src.services.trip_service import TripService
        svc = TripService()

        # 不需要构造完整 self，直接调用方法
        await svc._post_chat_tasks(conversation_id=99, user_message="帮我规划 3 天北京行程")

    # 1. enqueue 被调用 1 次
    mock_tq.enqueue.assert_awaited_once()
    # 2. 第一个位置参数是 post_chat_followup 函数
    from src.services.tasks.post_chat import post_chat_followup
    enqueue_args, enqueue_kwargs = mock_tq.enqueue.call_args
    assert enqueue_args[0] is post_chat_followup
    # 3. kwargs 正确
    assert enqueue_kwargs["conversation_id"] == 99
    assert enqueue_kwargs["user_message"] == "帮我规划 3 天北京行程"
    assert enqueue_kwargs["is_planning"] is True  # is_planning_request(...)
    assert enqueue_kwargs["job_id"] == "post_chat:followup:99"


# ---------------------------------------------------------------------------
# 测试 7：trip_service._post_chat_tasks 非规划场景
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trip_service_post_chat_tasks_is_planning_false():
    """is_planning_request 返回 False 时，enqueue 的 is_planning=False。"""
    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock(return_value="fake-job-id")

    with patch("src.services.task_queue.get_task_queue", return_value=mock_tq):
        from src.services.trip_service import TripService
        svc = TripService()

        await svc._post_chat_tasks(
            conversation_id=100, user_message="你好",
        )

    mock_tq.enqueue.assert_awaited_once()
    _, enqueue_kwargs = mock_tq.enqueue.call_args
    assert enqueue_kwargs["is_planning"] is False
    assert enqueue_kwargs["job_id"] == "post_chat:followup:100"


# ---------------------------------------------------------------------------
# 测试 8：trip_service._post_chat_tasks 入队失败不抛
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trip_service_post_chat_tasks_enqueue_failure_does_not_raise():
    """enqueue 抛错时：trip_service 静默吞掉（不能让流式响应报错）。"""
    mock_tq = MagicMock()
    mock_tq.enqueue = AsyncMock(side_effect=ConnectionError("Redis 断开"))

    with patch("src.services.task_queue.get_task_queue", return_value=mock_tq):
        from src.services.trip_service import TripService
        svc = TripService()

        # 不抛错
        await svc._post_chat_tasks(
            conversation_id=101, user_message="x",
        )

    mock_tq.enqueue.assert_awaited_once()
