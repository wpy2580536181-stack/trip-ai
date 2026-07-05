"""Tests for Trip Service — recommend + chat_stream"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.services.trip_service import TripService
from src.models.trip import Trip
from src.models.conversation import Conversation
from src.models.user import User
from src.utils.security import hash_password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db_session, username="testuser"):
    user = User(
        username=username,
        email=f"{username}@example.com",
        password=hash_password("Test@123"),
        nickname="Test User",
        role_id=2,
        status=1,
    )
    db_session.add(user)
    return user


def _mock_async_session(db_session):
    """Return a patcher that makes async_session() yield the test db_session."""
    @asynccontextmanager
    async def _fake_session():
        yield db_session
    return patch("src.services.trip_service.async_session", side_effect=lambda: _fake_session())


FAKE_PARSED = {
    "city": "成都",
    "days": 3,
    "totalBudget": 5000,
    "dailyItinerary": [{"day": 1, "morning": {"spot": "武侯祠"}}],
    "budgetBreakdown": {"accommodation": 1500, "food": 1000, "transportation": 800, "tickets": 700, "other": 1000},
    "tips": ["带好防晒"],
    "warnings": [],
}


# ===========================================================================
# TestTripRecommend
# ===========================================================================


class TestTripRecommend:
    """TripService.recommend test cases"""

    @pytest.mark.asyncio
    async def test_recommend_param_validation(self):
        """无效参数（负预算、0天数、超范围预算）抛 ValueError"""
        svc = TripService()

        with pytest.raises(ValueError, match="预算或天数不符合要求"):
            await svc.recommend(city="成都", budget=-100, days=3)

        with pytest.raises(ValueError, match="预算或天数不符合要求"):
            await svc.recommend(city="成都", budget=5000, days=0)

        with pytest.raises(ValueError, match="预算或天数不符合要求"):
            await svc.recommend(city="成都", budget=2_000_000, days=3)

        with pytest.raises(ValueError, match="预算或天数不符合要求"):
            await svc.recommend(city="成都", budget=5000, days=31)

    @pytest.mark.asyncio
    async def test_recommend_happy_path(self, db_session: AsyncSession):
        """mock AgentEngine → 返回行程数据 → 持久化到 DB"""
        user = _make_user(db_session)
        await db_session.commit()

        svc = TripService()
        mock_engine = MagicMock()
        mock_engine.recommend = AsyncMock(return_value={"parsed": FAKE_PARSED})

        with patch("src.services.trip_service.get_agent_engine", return_value=mock_engine), \
             _mock_async_session(db_session), \
             patch("src.services.trip_service.trip_log"):
            result = await svc.recommend(
                city="成都",
                budget=5000,
                days=3,
                user_id=user.id,
                departure_city="北京",
            )

        assert result["success"] is True
        assert result["data"]["city"] == "成都"
        assert result["data"]["days"] == 3
        assert result["data"]["id"] is not None

        # Verify trip persisted to DB
        trip_id = result["data"]["id"]
        db_result = await db_session.execute(select(Trip).where(Trip.id == trip_id))
        trip = db_result.scalar_one_or_none()
        assert trip is not None
        assert trip.city == "成都"
        assert trip.days == 3
        assert trip.budget == 5000
        assert trip.user_id == user.id

    @pytest.mark.asyncio
    async def test_recommend_llm_error(self):
        """LLM 调用失败时优雅降级（抛 ValueError）"""
        svc = TripService()
        mock_engine = MagicMock()
        mock_engine.recommend = AsyncMock(side_effect=RuntimeError("LLM API timeout"))

        with patch("src.services.trip_service.get_agent_engine", return_value=mock_engine), \
             patch("src.services.trip_service.trip_log"):
            with pytest.raises(ValueError, match="行程推荐失败"):
                await svc.recommend(city="成都", budget=5000, days=3)

    @pytest.mark.asyncio
    async def test_recommend_persist_trip(self, db_session: AsyncSession):
        """Trip 记录正确写入数据库（city, days, budget, content）"""
        user = _make_user(db_session)
        await db_session.commit()

        svc = TripService()
        mock_engine = MagicMock()
        mock_engine.recommend = AsyncMock(return_value={"parsed": FAKE_PARSED})

        with patch("src.services.trip_service.get_agent_engine", return_value=mock_engine), \
             _mock_async_session(db_session), \
             patch("src.services.trip_service.trip_log"):
            result = await svc.recommend(
                city="成都",
                budget=5000,
                days=3,
                user_id=user.id,
            )

        trip_id = result["data"]["id"]
        assert trip_id is not None

        db_result = await db_session.execute(select(Trip).where(Trip.id == trip_id))
        trip = db_result.scalar_one_or_none()
        assert trip is not None
        assert trip.city == "成都"
        assert trip.days == 3
        assert trip.budget == 5000
        assert isinstance(trip.content, dict)
        assert trip.content["city"] == "成都"
        assert trip.status == "completed"


# ===========================================================================
# TestTripChatStream
# ===========================================================================


class TestTripChatStream:
    """TripService.chat_stream basic tests"""

    @pytest.mark.asyncio
    async def test_chat_stream_creates_conversation(self, db_session: AsyncSession):
        """无 conversationId 时自动创建新对话"""
        user = _make_user(db_session)
        await db_session.commit()

        svc = TripService()
        mock_conv = Conversation(id=42, user_id=user.id, title="新对话")

        with patch("src.services.trip_service._get_or_create_conversation", new_callable=AsyncMock, return_value=mock_conv), \
             patch("src.services.trip_service._save_message", new_callable=AsyncMock, return_value=1), \
             patch("src.services.trip_service._update_message", new_callable=AsyncMock), \
             patch("src.services.trip_service.get_agent_engine") as mock_get_engine, \
             patch("src.services.trip_service.auto_title", new_callable=AsyncMock), \
             patch("src.services.trip_service.async_session") as mock_session_ctx, \
             patch("src.services.trip_service.trip_log"):

            mock_engine = MagicMock()

            async def fake_chat(user_id, message, conversation_id, message_id, on_event):
                await on_event({"type": "complete", "content": "你好！", "usage": {"total_tokens": 10}})

            mock_engine.chat = fake_chat
            mock_get_engine.return_value = mock_engine

            mock_sess = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            events = []
            async for event in svc.chat_stream(user_id=user.id, message="你好"):
                events.append(event)

            event_types = [e.get("type") for e in events]
            assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_chat_stream_uses_existing_conversation(self, db_session: AsyncSession):
        """有 conversationId 时使用已有对话"""
        user = _make_user(db_session)
        await db_session.commit()

        existing_conv = Conversation(user_id=user.id, title="已有对话")
        db_session.add(existing_conv)
        await db_session.commit()
        await db_session.refresh(existing_conv)

        svc = TripService()

        with patch("src.services.trip_service._get_or_create_conversation", new_callable=AsyncMock, return_value=existing_conv) as mock_get_conv, \
             patch("src.services.trip_service._save_message", new_callable=AsyncMock, return_value=1), \
             patch("src.services.trip_service._update_message", new_callable=AsyncMock), \
             patch("src.services.trip_service.get_agent_engine") as mock_get_engine, \
             patch("src.services.trip_service.async_session") as mock_session_ctx, \
             patch("src.services.trip_service.trip_log"):

            mock_engine = MagicMock()

            async def fake_chat(user_id, message, conversation_id, message_id, on_event):
                await on_event({"type": "complete", "content": "好的", "usage": {"total_tokens": 5}})

            mock_engine.chat = fake_chat
            mock_get_engine.return_value = mock_engine

            mock_sess = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            events = []
            async for event in svc.chat_stream(
                user_id=user.id,
                message="继续聊",
                conversation_id=existing_conv.id,
            ):
                events.append(event)

            mock_get_conv.assert_awaited_once_with(user.id, existing_conv.id)

            event_types = [e.get("type") for e in events]
            assert "complete" in event_types
