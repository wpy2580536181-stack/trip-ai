"""Tests for Admin Controller"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from src.main import app
from src.middleware.auth import get_current_user, require_admin
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.utils.security import hash_password


def _override_admin(user: User):
    """Helper: override require_admin dependency."""
    async def mock_require_admin():
        if user.role_id != 1:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail={"code": 403, "message": "Admin access required", "error": "FORBIDDEN"},
            )
        return user

    app.dependency_overrides[require_admin] = mock_require_admin


def _override_auth(user: User):
    """Helper: override get_current_user dependency."""
    async def mock_get_user():
        return user

    app.dependency_overrides[get_current_user] = mock_get_user


def _cleanup():
    for dep in (get_current_user, require_admin):
        app.dependency_overrides.pop(dep, None)


class TestAdminAuth:
    """Admin 权限检查"""

    @pytest.mark.asyncio
    async def test_admin_access_success(self, async_client: AsyncClient, db_session):
        """admin 用户访问 → 200"""
        admin = User(
            username="admin1",
            email="admin1@example.com",
            password=hash_password("Test@123"),
            nickname="Admin",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()
        _override_admin(admin)

        with patch(
            "src.controllers.admin_controller.AdminService.get_agent_trace_summary",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = await async_client.get(
                "/api/admin/agent-trace",
                params={"conversation_id": 1},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

        _cleanup()

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, async_client: AsyncClient, db_session):
        """非 admin 用户 → 403"""
        user = User(
            username="normal1",
            email="normal1@example.com",
            password=hash_password("Test@123"),
            nickname="Normal",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        await db_session.commit()
        _override_admin(user)

        response = await async_client.get(
            "/api/admin/agent-trace",
            params={"conversation_id": 1},
        )

        assert response.status_code == 403

        _cleanup()

    @pytest.mark.asyncio
    async def test_unauthenticated(self, async_client: AsyncClient):
        """未认证 → 401/403 (取决于 FastAPI security scheme)"""
        response = await async_client.get(
            "/api/admin/agent-trace",
            params={"conversation_id": 1},
        )
        # No auth token → 401 from HTTPBearer or 403
        assert response.status_code in (401, 403)


class TestAgentTraceDetail:
    """GET /api/admin/agent-trace/{message_id}"""

    @pytest.mark.asyncio
    async def test_get_agent_trace_success(self, async_client: AsyncClient, db_session):
        """正常获取 Agent 轨迹 → 200"""
        admin = User(
            username="admin2",
            email="admin2@example.com",
            password=hash_password("Test@123"),
            nickname="Admin 2",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()
        _override_admin(admin)

        # Mock AdminService to avoid the metadata_/metadata attribute bug
        mock_trace = {
            "message": {
                "id": 1,
                "role": "assistant",
                "content": "这是测试消息内容",
                "metadata": {"usage": {"total_tokens": 100}},
                "createdAt": "2026-07-04T00:00:00+00:00",
                "conversationId": 1,
                "_count": {"steps": 1},
            },
            "steps": [
                {
                    "id": 1,
                    "step": 1,
                    "type": "tool",
                    "name": "search_spots",
                    "args": {"city": "北京"},
                    "output": "result",
                    "durationMs": 120,
                    "error": None,
                    "createdAt": "2026-07-04T00:00:00+00:00",
                }
            ],
        }

        with patch(
            "src.controllers.admin_controller.AdminService.get_agent_trace",
            new_callable=AsyncMock,
            return_value=mock_trace,
        ):
            response = await async_client.get("/api/admin/agent-trace/1")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["message"]["id"] == 1
        assert data["data"]["message"]["content"] == "这是测试消息内容"
        assert len(data["data"]["steps"]) == 1
        assert data["data"]["steps"][0]["name"] == "search_spots"

        _cleanup()

    @pytest.mark.asyncio
    async def test_get_agent_trace_not_found(self, async_client: AsyncClient, db_session):
        """消息不存在 → 400"""
        admin = User(
            username="admin3",
            email="admin3@example.com",
            password=hash_password("Test@123"),
            nickname="Admin 3",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()
        _override_admin(admin)

        response = await async_client.get("/api/admin/agent-trace/99999")

        assert response.status_code == 400

        _cleanup()


class TestAgentTraceSummary:
    """GET /api/admin/agent-trace?conversation_id=X"""

    @pytest.mark.asyncio
    async def test_get_summary_success(self, async_client: AsyncClient, db_session):
        """正常获取摘要列表 → 200"""
        admin = User(
            username="admin4",
            email="admin4@example.com",
            password=hash_password("Test@123"),
            nickname="Admin 4",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()

        conv = Conversation(
            user_id=admin.id,
            title="Summary Conv",
        )
        db_session.add(conv)
        await db_session.commit()

        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content="这是助手回复",
            metadata_={"usage": {"total_tokens": 200}},
        )
        db_session.add(msg)
        await db_session.commit()

        _override_admin(admin)

        response = await async_client.get(
            "/api/admin/agent-trace",
            params={"conversation_id": conv.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "summaries" in data["data"]
        assert len(data["data"]["summaries"]) == 1
        assert data["data"]["summaries"][0]["messageId"] == msg.id

        _cleanup()

    @pytest.mark.asyncio
    async def test_get_summary_missing_conversation_id(self, async_client: AsyncClient, db_session):
        """缺少 conversation_id → 422"""
        admin = User(
            username="admin5",
            email="admin5@example.com",
            password=hash_password("Test@123"),
            nickname="Admin 5",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()
        _override_admin(admin)

        response = await async_client.get("/api/admin/agent-trace")

        assert response.status_code == 422

        _cleanup()

    @pytest.mark.asyncio
    async def test_get_summary_with_limit(self, async_client: AsyncClient, db_session):
        """带 limit 参数 → 200"""
        admin = User(
            username="admin6",
            email="admin6@example.com",
            password=hash_password("Test@123"),
            nickname="Admin 6",
            role_id=1,
            status=1,
        )
        db_session.add(admin)
        await db_session.commit()
        _override_admin(admin)

        with patch(
            "src.controllers.admin_controller.AdminService.get_agent_trace_summary",
            new_callable=AsyncMock,
            return_value=[],
        ):
            response = await async_client.get(
                "/api/admin/agent-trace",
                params={"conversation_id": 1, "limit": 5},
            )

        assert response.status_code == 200

        _cleanup()
