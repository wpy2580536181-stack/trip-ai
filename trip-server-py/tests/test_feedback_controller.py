"""Tests for Feedback Controller"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.middleware.auth import get_current_user, require_admin
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.feedback import Feedback


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _seed_data(db: AsyncSession, username="ctluser") -> tuple[User, Conversation, Message]:
    """Create User → Conversation → Message chain for controller tests."""
    user = User(
        username=username, email=f"{username}@example.com",
        password="hashed", nickname=username, role_id=2, status=1,
    )
    db.add(user)
    await db.flush()

    conv = Conversation(user_id=user.id, title="test conv")
    db.add(conv)
    await db.flush()

    msg = Message(conversation_id=conv.id, role="assistant", content="hello")
    db.add(msg)
    await db.flush()

    await db.commit()
    return user, conv, msg


def _make_admin(db_session: AsyncSession):
    """Helper to override require_admin with a fresh admin User object."""
    admin = User(
        id=99, username="admin", email="admin@test.com",
        password="hashed", nickname="Admin", role_id=1, status=1,
    )

    async def _override():
        return admin

    app.dependency_overrides[require_admin] = _override
    return admin


def _make_user(user: User):
    """Helper to override get_current_user with a specific user."""

    async def _override():
        return user

    app.dependency_overrides[get_current_user] = _override


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFeedbackController:
    """Test cases for Feedback Controller"""

    # ---- submit feedback --------------------------------------------------

    @pytest.mark.asyncio
    async def test_submit_unauthenticated(self, async_client: AsyncClient):
        """无 token → 401"""
        response = await async_client.post(
            "/api/feedback",
            json={"messageId": 1, "conversationId": 1, "rating": 1},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_submit_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """正常提交 → 200"""
        user, conv, msg = await _seed_data(db_session)
        _make_user(user)

        response = await async_client.post(
            "/api/feedback",
            json={"messageId": msg.id, "conversationId": conv.id, "rating": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["rating"] == 1

        app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_submit_invalid_body(self, async_client: AsyncClient, db_session: AsyncSession):
        """缺少必填字段 → 422"""
        user, _, _ = await _seed_data(db_session, username="inv_body")
        _make_user(user)

        response = await async_client.post(
            "/api/feedback",
            json={"rating": 1},  # missing messageId / conversationId
        )

        assert response.status_code == 422
        app.dependency_overrides.pop(get_current_user, None)

    # ---- message feedback stats ------------------------------------------

    @pytest.mark.asyncio
    async def test_get_message_stats_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """200 + 正确格式"""
        user, conv, msg = await _seed_data(db_session, username="mstats")
        # Create a feedback so stats aren't all-zero
        _make_user(user)
        await async_client.post(
            "/api/feedback",
            json={"messageId": msg.id, "conversationId": conv.id, "rating": 1},
        )

        response = await async_client.get(f"/api/feedback/message/{msg.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        stats = data["data"]
        assert "up" in stats
        assert "down" in stats
        assert "total" in stats
        assert "satisfactionRate" in stats

        app.dependency_overrides.pop(get_current_user, None)

    # ---- global stats (admin) --------------------------------------------

    @pytest.mark.asyncio
    async def test_get_global_stats_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """admin 访问 → 200"""
        _make_admin(db_session)

        response = await async_client.get("/api/feedback/stats", params={"days": 7})

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert "totalCount" in data["data"]
        assert "recentDownComments" in data["data"]

        app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.asyncio
    async def test_get_global_stats_non_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """非 admin → 403"""
        user, _, _ = await _seed_data(db_session, username="nonadmin_stats")
        # Override get_current_user (not require_admin) so require_admin checks role_id=2 → 403
        _make_user(user)

        response = await async_client.get("/api/feedback/stats", params={"days": 7})

        assert response.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)

    # ---- admin: list_for_message -----------------------------------------

    @pytest.mark.asyncio
    async def test_list_for_message_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """admin 访问 → 200"""
        _make_admin(db_session)

        response = await async_client.get("/api/feedback/list/1")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

        app.dependency_overrides.pop(require_admin, None)

    @pytest.mark.asyncio
    async def test_list_for_message_non_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """非 admin → 403"""
        user, _, _ = await _seed_data(db_session, username="nonadmin_list")
        _make_user(user)

        response = await async_client.get("/api/feedback/list/1")

        assert response.status_code == 403

        app.dependency_overrides.pop(get_current_user, None)

    # ---- admin: high token low satisfaction ------------------------------

    @pytest.mark.asyncio
    async def test_high_token_low_satisfaction_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """admin → 200"""
        _make_admin(db_session)

        response = await async_client.get(
            "/api/feedback/admin/high-token-low-satisfaction",
            params={"days": 7, "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

        app.dependency_overrides.pop(require_admin, None)

    # ---- admin: daily stats ---------------------------------------------

    @pytest.mark.asyncio
    async def test_daily_stats_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """admin → 200"""
        _make_admin(db_session)

        response = await async_client.get(
            "/api/feedback/admin/daily-stats",
            params={"days": 7},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200

        app.dependency_overrides.pop(require_admin, None)

    # ---- admin: test alert ----------------------------------------------

    @pytest.mark.asyncio
    async def test_test_alert_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """admin → 200"""
        _make_admin(db_session)

        # Mock alert_scheduler.tick to avoid side-effects
        from src.services.alert import alert_scheduler as _sched
        original_tick = _sched.tick

        async def _mock_tick():
            return {"shouldAlert": False, "sent": False, "reason": "mock"}

        _sched.tick = _mock_tick

        try:
            response = await async_client.post("/api/feedback/admin/test-alert")
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 200
        finally:
            _sched.tick = original_tick
            app.dependency_overrides.pop(require_admin, None)
