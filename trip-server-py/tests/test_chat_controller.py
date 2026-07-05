"""Tests for Chat Controller + Trip Controller (chat / recommend / optimize)"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

from src.main import app
from src.middleware.auth import get_current_user, require_admin
from src.middleware.concurrency_guard import concurrency_guard_dependency
from src.middleware.token_budget_guard import token_budget_guard_dependency
from src.models.user import User
from src.utils.security import hash_password


def _override_auth(user: User):
    """Helper: override auth + middleware dependencies for chat/trip endpoints."""
    async def mock_get_user():
        return user

    async def noop():
        return None

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[concurrency_guard_dependency] = noop
    app.dependency_overrides[token_budget_guard_dependency] = noop


def _cleanup_overrides():
    """Helper: remove all overrides."""
    for dep in (
        get_current_user,
        require_admin,
        concurrency_guard_dependency,
        token_budget_guard_dependency,
    ):
        app.dependency_overrides.pop(dep, None)


class TestChatEndpoint:
    """POST /api/trip/chat — SSE 流式对话"""

    @pytest.mark.asyncio
    async def test_chat_success_sse(self, async_client: AsyncClient, db_session):
        """正常对话 → 200 + text/event-stream"""
        user = User(
            username="chatuser",
            email="chat@example.com",
            password=hash_password("Test@123"),
            nickname="Chat User",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        # Mock trip_service.chat_stream to yield simple events
        async def fake_chat_stream(**kwargs):
            yield {"type": "delta", "data": "你好"}
            yield {"type": "complete", "data": {"conversationId": 1, "usage": {}}}

        with patch(
            "src.controllers.chat_controller.trip_service.chat_stream",
            side_effect=fake_chat_stream,
        ):
            # Also mock create_resumable_stream to bypass Redis
            from src.utils.stream import sse_event, sse_end_event

            async def fake_create_resumable_stream(user_id, conversation_id, source):
                async for payload in source:
                    yield sse_event(payload)
                yield sse_end_event()

            with patch(
                "src.controllers.chat_controller.create_resumable_stream",
                side_effect=fake_create_resumable_stream,
            ):
                response = await async_client.post(
                    "/api/trip/chat",
                    json={"message": "帮我规划一个北京三日游"},
                )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_chat_unauthorized(self, async_client: AsyncClient):
        """未认证 → 401"""
        response = await async_client.post(
            "/api/trip/chat",
            json={"message": "hello"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_chat_empty_message(self, async_client: AsyncClient, db_session):
        """空消息 → 422 (Pydantic min_length=1)"""
        user = User(
            username="chatuser2",
            email="chat2@example.com",
            password=hash_password("Test@123"),
            nickname="Chat User 2",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.post(
            "/api/trip/chat",
            json={"message": ""},
        )
        assert response.status_code == 422

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_chat_missing_message(self, async_client: AsyncClient, db_session):
        """缺少 message 字段 → 422"""
        user = User(
            username="chatuser3",
            email="chat3@example.com",
            password=hash_password("Test@123"),
            nickname="Chat User 3",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.post(
            "/api/trip/chat",
            json={},
        )
        assert response.status_code == 422

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_chat_resume_invalid_last_event_id(self, async_client: AsyncClient, db_session):
        """续传时 Last-Event-ID 非数字 → 400"""
        user = User(
            username="chatuser4",
            email="chat4@example.com",
            password=hash_password("Test@123"),
            nickname="Chat User 4",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.post(
            "/api/trip/chat",
            json={"message": "hi"},
            headers={
                "X-Stream-Id": "some-stream-id",
                "Last-Event-ID": "not-a-number",
            },
        )
        assert response.status_code == 400

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_chat_resume_negative_last_event_id(self, async_client: AsyncClient, db_session):
        """续传时 Last-Event-ID 为负数 → 400"""
        user = User(
            username="chatuser5",
            email="chat5@example.com",
            password=hash_password("Test@123"),
            nickname="Chat User 5",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.post(
            "/api/trip/chat",
            json={"message": "hi"},
            headers={
                "X-Stream-Id": "some-stream-id",
                "Last-Event-ID": "-1",
            },
        )
        assert response.status_code == 400

        _cleanup_overrides()


class TestRecommendEndpoint:
    """POST /api/trip/recommend — 行程推荐"""

    @pytest.mark.asyncio
    async def test_recommend_success(self, async_client: AsyncClient, db_session):
        """正常推荐 → 200 + 行程数据"""
        user = User(
            username="reco_user",
            email="reco@example.com",
            password=hash_password("Test@123"),
            nickname="Reco User",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        mock_result = {
            "success": True,
            "data": {
                "city": "北京",
                "days": 3,
                "totalBudget": 5000,
                "dailyItinerary": [],
                "budgetBreakdown": {},
                "tips": ["带好防晒"],
            },
        }

        with patch(
            "src.controllers.trip_controller.trip_service.recommend",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await async_client.post(
                "/api/trip/recommend",
                json={"city": "北京", "budget": 5000, "days": 3},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["city"] == "北京"

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_recommend_unauthorized(self, async_client: AsyncClient):
        """未认证 → 401"""
        response = await async_client.post(
            "/api/trip/recommend",
            json={"city": "北京", "budget": 5000, "days": 3},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_recommend_invalid_params(self, async_client: AsyncClient, db_session):
        """无效参数（budget 超限）→ 422"""
        user = User(
            username="reco_user2",
            email="reco2@example.com",
            password=hash_password("Test@123"),
            nickname="Reco User 2",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.post(
            "/api/trip/recommend",
            json={"city": "北京", "budget": 10, "days": 3},
        )
        # budget < 50 → 422
        assert response.status_code == 422

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_recommend_service_error(self, async_client: AsyncClient, db_session):
        """trip_service 抛 ValueError → 400"""
        user = User(
            username="reco_user3",
            email="reco3@example.com",
            password=hash_password("Test@123"),
            nickname="Reco User 3",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        with patch(
            "src.controllers.trip_controller.trip_service.recommend",
            new_callable=AsyncMock,
            side_effect=ValueError("参数错误"),
        ):
            response = await async_client.post(
                "/api/trip/recommend",
                json={"city": "北京", "budget": 5000, "days": 3},
            )

        assert response.status_code == 400

        _cleanup_overrides()


class TestOptimizeEndpoint:
    """POST /api/trip/optimize — 行程优化"""

    @pytest.mark.asyncio
    async def test_optimize_success(self, async_client: AsyncClient, db_session):
        """正常优化 → 200 + 优化结果"""
        user = User(
            username="opt_user",
            email="opt@example.com",
            password=hash_password("Test@123"),
            nickname="Opt User",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        mock_result = {
            "success": True,
            "data": {
                "city": "北京",
                "days": 3,
                "totalBudget": 5000,
                "dailyItinerary": [],
                "budgetBreakdown": {},
                "tips": [],
            },
        }

        with patch(
            "src.controllers.trip_controller.optimize_trip",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = await async_client.post(
                "/api/trip/optimize",
                json={"tripId": 1, "instruction": "减少预算"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_optimize_unauthorized(self, async_client: AsyncClient):
        """未认证 → 401"""
        response = await async_client.post(
            "/api/trip/optimize",
            json={"tripId": 1},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_optimize_not_found(self, async_client: AsyncClient, db_session):
        """行程不存在 → 404"""
        user = User(
            username="opt_user2",
            email="opt2@example.com",
            password=hash_password("Test@123"),
            nickname="Opt User 2",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        with patch(
            "src.controllers.trip_controller.optimize_trip",
            new_callable=AsyncMock,
            side_effect=ValueError("行程不存在"),
        ):
            response = await async_client.post(
                "/api/trip/optimize",
                json={"tripId": 999},
            )

        assert response.status_code == 404

        _cleanup_overrides()

    @pytest.mark.asyncio
    async def test_optimize_invalid_params(self, async_client: AsyncClient, db_session):
        """无效参数（tripId=0）→ 422"""
        user = User(
            username="opt_user3",
            email="opt3@example.com",
            password=hash_password("Test@123"),
            nickname="Opt User 3",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.post(
            "/api/trip/optimize",
            json={"tripId": 0},
        )
        assert response.status_code == 422

        _cleanup_overrides()
