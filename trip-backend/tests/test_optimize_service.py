"""Tests for Optimize Service — optimize_trip"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.services.optimize_service import optimize_trip, _extract_json, _validate_parsed
from src.models.trip import Trip
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


def _make_trip(db_session, user_id, city="成都", days=3, budget=5000, content=None):
    trip = Trip(
        user_id=user_id,
        from_city="北京",
        city=city,
        days=days,
        budget=budget,
        content=content or {"city": city, "days": days, "totalBudget": budget, "dailyItinerary": [], "budgetBreakdown": {}, "tips": []},
        status="completed",
    )
    db_session.add(trip)
    return trip


def _mock_async_session(db_session):
    """Return a patcher that makes async_session() yield the test db_session."""
    @asynccontextmanager
    async def _fake_session():
        yield db_session
    return patch("src.services.optimize_service.async_session", side_effect=lambda: _fake_session())


VALID_OPTIMIZED_JSON = {
    "city": "成都",
    "days": 3,
    "totalBudget": 5000,
    "dailyItinerary": [{"day": 1, "morning": {"spot": "锦里"}}],
    "budgetBreakdown": {"accommodation": 1500, "food": 1000, "transportation": 800, "tickets": 700, "other": 1000},
    "tips": ["穿舒适鞋"],
    "warnings": [],
}


# ===========================================================================
# TestOptimizeTrip
# ===========================================================================


class TestOptimizeTrip:
    """optimize_trip test cases"""

    @pytest.mark.asyncio
    async def test_optimize_invalid_trip_id(self):
        """不存在的 trip_id → ValueError"""
        with patch("src.services.optimize_service._find_trip", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="行程不存在"):
                await optimize_trip(trip_id=99999, user_id=1)

    @pytest.mark.asyncio
    async def test_optimize_idor_protection(self, db_session: AsyncSession):
        """其他用户的 trip → 拒绝（_find_trip returns None when user_id mismatch）"""
        owner = _make_user(db_session, "owner")
        await db_session.commit()

        trip = _make_trip(db_session, user_id=owner.id)
        await db_session.commit()
        await db_session.refresh(trip)

        # Another user (id=9999) tries to optimize → _find_trip returns None
        with patch("src.services.optimize_service._find_trip", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="行程不存在"):
                await optimize_trip(trip_id=trip.id, user_id=9999)

    @pytest.mark.asyncio
    async def test_optimize_happy_path(self, db_session: AsyncSession):
        """mock LLM → 返回优化行程 → 新 Trip 的 parent_trip_id 关联原行程"""
        user = _make_user(db_session)
        await db_session.commit()

        trip = _make_trip(db_session, user_id=user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        import json
        llm_output = json.dumps(VALID_OPTIMIZED_JSON, ensure_ascii=False)
        mock_llm = MagicMock()
        mock_llm.temperature = 0.5
        mock_response = MagicMock()
        mock_response.content = llm_output
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("src.services.optimize_service.create_llm", return_value=mock_llm), \
             _mock_async_session(db_session), \
             patch("src.services.optimize_service.trip_log"):
            result = await optimize_trip(
                trip_id=trip.id,
                instruction="减少步行",
                user_id=user.id,
            )

        assert result["success"] is True
        assert result["data"]["city"] == "成都"
        assert result["data"]["id"] is not None

        # Verify new trip has parent_trip_id pointing to original
        new_trip_id = result["data"]["id"]
        db_result = await db_session.execute(select(Trip).where(Trip.id == new_trip_id))
        new_trip = db_result.scalar_one_or_none()
        assert new_trip is not None
        assert new_trip.parent_trip_id == trip.id

    @pytest.mark.asyncio
    async def test_optimize_json_parse_retry(self, db_session: AsyncSession):
        """LLM 返回格式错误时重试解析"""
        user = _make_user(db_session)
        await db_session.commit()

        trip = _make_trip(db_session, user_id=user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        import json
        valid_json_str = json.dumps(VALID_OPTIMIZED_JSON, ensure_ascii=False)

        call_count = 0

        async def fake_ainvoke(messages):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:
                resp.content = "这不是 JSON，是一些乱码 @@##$$"
            else:
                resp.content = valid_json_str
            return resp

        mock_llm = MagicMock()
        mock_llm.temperature = 0.5
        mock_llm.ainvoke = fake_ainvoke

        with patch("src.services.optimize_service.create_llm", return_value=mock_llm), \
             _mock_async_session(db_session), \
             patch("src.services.optimize_service.trip_log"), \
             patch("src.services.optimize_service.asyncio.sleep", new_callable=AsyncMock):
            result = await optimize_trip(
                trip_id=trip.id,
                instruction="优化一下",
                user_id=user.id,
            )

        assert result["success"] is True
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_optimize_empty_instruction(self, db_session: AsyncSession):
        """空 instruction 时使用默认 prompt（不报错）"""
        user = _make_user(db_session)
        await db_session.commit()

        trip = _make_trip(db_session, user_id=user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        import json
        llm_output = json.dumps(VALID_OPTIMIZED_JSON, ensure_ascii=False)
        mock_llm = MagicMock()
        mock_llm.temperature = 0.5
        mock_response = MagicMock()
        mock_response.content = llm_output
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)

        with patch("src.services.optimize_service.create_llm", return_value=mock_llm), \
             _mock_async_session(db_session), \
             patch("src.services.optimize_service.trip_log"):
            result = await optimize_trip(
                trip_id=trip.id,
                instruction="",
                user_id=user.id,
            )

        assert result["success"] is True
        assert result["data"]["city"] == "成都"


# ===========================================================================
# TestExtractJson / TestValidateParsed (pure functions)
# ===========================================================================


class TestExtractJson:
    """_extract_json pure function tests"""

    def test_extract_valid_json(self):
        text = 'some prefix {"city": "成都"} some suffix'
        assert _extract_json(text) == '{"city": "成都"}'

    def test_extract_no_json(self):
        with pytest.raises(ValueError, match="未找到 JSON 对象"):
            _extract_json("no json here at all")


class TestValidateParsed:
    """_validate_parsed pure function tests"""

    def test_valid_parsed(self):
        _validate_parsed(VALID_OPTIMIZED_JSON)

    def test_missing_field(self):
        incomplete = {"city": "成都"}
        with pytest.raises(ValueError, match="缺少必填字段"):
            _validate_parsed(incomplete)

    def test_not_dict(self):
        with pytest.raises(ValueError, match="JSON 根对象必须是字典"):
            _validate_parsed([1, 2, 3])
