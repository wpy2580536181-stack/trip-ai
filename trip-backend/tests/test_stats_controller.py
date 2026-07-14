"""Tests for Stats Controller"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.middleware.auth import get_current_user
from src.models.user import User
from src.utils.security import hash_password


def _override_auth(user: User):
    """Helper: override get_current_user dependency."""
    async def mock_get_user():
        return user

    app.dependency_overrides[get_current_user] = mock_get_user


def _cleanup():
    app.dependency_overrides.pop(get_current_user, None)


class TestTokenUsageSummary:
    """GET /api/stats/token-usage/summary"""

    @pytest.mark.asyncio
    async def test_token_summary_user_scope(self, async_client: AsyncClient, db_session):
        """user scope → 200 + 统计数据结构"""
        user = User(
            username="stats_user1",
            email="stats1@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 1",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/summary",
            params={"scope": "user"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "window" in data["data"]
        assert "current" in data["data"]["window"]
        assert "limit" in data["data"]["window"]

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_summary_global_forbidden(self, async_client: AsyncClient, db_session):
        """非 admin 用户请求 global scope → 403"""
        user = User(
            username="stats_user2",
            email="stats2@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 2",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/summary",
            params={"scope": "global"},
        )

        assert response.status_code == 403

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_summary_global_admin(self, async_client: AsyncClient, db_session):
        """admin 用户请求 global scope → 200"""
        admin = User(
            username="stats_admin",
            email="stats_admin@example.com",
            password=hash_password("Test@123"),
            nickname="Stats Admin",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()
        _override_auth(admin)

        response = await async_client.get(
            "/api/stats/token-usage/summary",
            params={"scope": "global"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_summary_unauthorized(self, async_client: AsyncClient):
        """未认证 → 401"""
        response = await async_client.get("/api/stats/token-usage/summary")
        assert response.status_code == 401


class TestTokenUsageStats:
    """GET /api/stats/token-usage/stats"""

    @pytest.mark.asyncio
    async def test_token_stats_user_scope(self, async_client: AsyncClient, db_session):
        """user scope → 200"""
        user = User(
            username="stats_user3",
            email="stats3@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 3",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/stats",
            params={"scope": "user"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "window" in data["data"]

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_stats_global_forbidden(self, async_client: AsyncClient, db_session):
        """非 admin → global → 403"""
        user = User(
            username="stats_user4",
            email="stats4@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 4",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/stats",
            params={"scope": "global"},
        )

        assert response.status_code == 403

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_stats_unauthorized(self, async_client: AsyncClient):
        """未认证 → 401"""
        response = await async_client.get("/api/stats/token-usage/stats")
        assert response.status_code == 401


class TestTokenUsageLogs:
    """GET /api/stats/token-usage/logs"""

    @pytest.mark.asyncio
    async def test_token_logs_user_scope(self, async_client: AsyncClient, db_session):
        """user scope → 200 + 日志结构"""
        user = User(
            username="stats_user5",
            email="stats5@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 5",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/logs",
            params={"scope": "user", "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "logs" in data["data"]
        assert isinstance(data["data"]["logs"], list)

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_logs_global_forbidden(self, async_client: AsyncClient, db_session):
        """非 admin → global → 403"""
        user = User(
            username="stats_user6",
            email="stats6@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 6",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/logs",
            params={"scope": "global"},
        )

        assert response.status_code == 403

        _cleanup()

    @pytest.mark.asyncio
    async def test_token_logs_unauthorized(self, async_client: AsyncClient):
        """未认证 → 401"""
        response = await async_client.get("/api/stats/token-usage/logs")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_token_logs_default_limit(self, async_client: AsyncClient, db_session):
        """不传 limit 使用默认值 50 → 200"""
        user = User(
            username="stats_user7",
            email="stats7@example.com",
            password=hash_password("Test@123"),
            nickname="Stats User 7",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_auth(user)

        response = await async_client.get(
            "/api/stats/token-usage/logs",
            params={"scope": "user"},
        )

        assert response.status_code == 200

        _cleanup()
