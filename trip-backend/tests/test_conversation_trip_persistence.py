"""Tests for ConversationService.get_by_trip_id + Trip-Conversation ORM relationship (T4)"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.conversation_service import ConversationService
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.trip import Trip
from src.models.user import User
from src.utils.security import hash_password
from src.exceptions import NotFoundException


# ---- Shared test helpers ----

def _make_user(db_session: AsyncSession, suffix: str = "") -> User:
    user = User(
        username=f"convuser{suffix}",
        email=f"conv{suffix}@example.com",
        password=hash_password("Test@123"),
        nickname=f"Conv User {suffix}",
        role_id=2,
        status=1,
    )
    db_session.add(user)
    return user


def _make_trip(db_session: AsyncSession, user_id: int) -> Trip:
    trip = Trip(
        user_id=user_id,
        from_city="Beijing",
        city="Shanghai",
        days=3,
        budget=5000,
        content={"itinerary": []},
        status="completed",
    )
    db_session.add(trip)
    return trip


def _make_conversation(
    db_session: AsyncSession,
    user_id: int,
    trip_id: int,
    title: str,
) -> Conversation:
    conv = Conversation(
        user_id=user_id,
        trip_id=trip_id,
        title=title,
        summary=None,
        summary_error=False,
        summary_at=None,
    )
    db_session.add(conv)
    return conv


class TestGetByTripId:
    """Test cases for ConversationService.get_by_trip_id"""

    @staticmethod
    def _make_user(db_session: AsyncSession, suffix: str = "") -> User:
        user = User(
            username=f"convuser{suffix}",
            email=f"conv{suffix}@example.com",
            password=hash_password("Test@123"),
            nickname=f"Conv User {suffix}",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        return user

    @staticmethod
    def _make_trip(db_session: AsyncSession, user_id: int) -> Trip:
        trip = Trip(
            user_id=user_id,
            from_city="Beijing",
            city="Shanghai",
            days=3,
            budget=5000,
            content={"itinerary": []},
            status="completed",
        )
        db_session.add(trip)
        return trip

    @staticmethod
    def _make_conversation(
        db_session: AsyncSession,
        user_id: int,
        trip_id: int,
        title: str,
    ) -> Conversation:
        conv = Conversation(
            user_id=user_id,
            trip_id=trip_id,
            title=title,
            summary=None,
            summary_error=False,
            summary_at=None,
        )
        db_session.add(conv)
        return conv

    @pytest.mark.asyncio
    async def test_get_by_trip_id_returns_latest(self, db_session: AsyncSession):
        """创建多个相同行程的对话，验证返回 updated_at 最新的那条"""
        user = _make_user(db_session, "latest")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()

        conv1 = _make_conversation(db_session, user.id, trip.id, "Conversation 1")
        await db_session.commit()
        conv2 = _make_conversation(db_session, user.id, trip.id, "Conversation 2")
        await db_session.commit()
        conv3 = _make_conversation(db_session, user.id, trip.id, "Conversation 3")
        await db_session.commit()

        # 明确设置时间顺序，确保 conv3 最新
        from datetime import datetime, timezone
        from sqlalchemy import update as sa_update

        await db_session.execute(
            sa_update(Conversation)
            .where(Conversation.id == conv1.id)
            .values(updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        )
        await db_session.execute(
            sa_update(Conversation)
            .where(Conversation.id == conv2.id)
            .values(updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc))
        )
        await db_session.execute(
            sa_update(Conversation)
            .where(Conversation.id == conv3.id)
            .values(updated_at=datetime(2024, 1, 3, tzinfo=timezone.utc))
        )
        await db_session.commit()

        result = await ConversationService.get_by_trip_id(
            db_session, trip.id, user.id
        )

        assert result.id == conv3.id
        assert result.title == "Conversation 3"

    @pytest.mark.asyncio
    async def test_get_by_trip_id_404_when_no_conversation(self, db_session: AsyncSession):
        """行程存在但无关联对话 → NotFoundException"""
        user = _make_user(db_session, "noconv")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()

        with pytest.raises(NotFoundException) as exc_info:
            await ConversationService.get_by_trip_id(
                db_session, trip.id, user.id
            )

        assert "行程关联对话" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_by_trip_id_404_when_trip_not_found(self, db_session: AsyncSession):
        """行程不存在 → NotFoundException"""
        user = _make_user(db_session, "notrip")
        await db_session.commit()

        with pytest.raises(NotFoundException) as exc_info:
            await ConversationService.get_by_trip_id(
                db_session, 99999, user.id
            )

        assert "行程" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_by_trip_id_forbidden_for_other_user(self, db_session: AsyncSession):
        """其他用户的行程 → NotFoundException"""
        owner = _make_user(db_session, "owner")
        other = _make_user(db_session, "other")
        await db_session.commit()

        trip = _make_trip(db_session, owner.id)
        await db_session.commit()

        with pytest.raises(NotFoundException) as exc_info:
            await ConversationService.get_by_trip_id(
                db_session, trip.id, other.id
            )

        assert "行程" in str(exc_info.value)


class TestTripConversationRelationship:
    """Test cases for Trip <-> Conversation ORM relationship (T4)"""

    @staticmethod
    def _make_user(db_session: AsyncSession, suffix: str = "") -> User:
        user = User(
            username=f"tripuser{suffix}",
            email=f"trip{suffix}@example.com",
            password=hash_password("Test@123"),
            nickname=f"Trip User {suffix}",
            role_id=2,
            status=1,
        )
        db_session.add(user)
        return user

    @staticmethod
    def _make_trip(db_session: AsyncSession, user_id: int) -> Trip:
        trip = Trip(
            user_id=user_id,
            from_city="Beijing",
            city="Shanghai",
            days=3,
            budget=5000,
            content={"itinerary": []},
            status="completed",
        )
        db_session.add(trip)
        return trip

    @pytest.mark.asyncio
    async def test_trip_can_access_related_conversations(self, db_session: AsyncSession):
        """Test that a Trip can access its related conversations via trip.conversations (T4-AC1)"""
        user = _make_user(db_session, "rel")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        conv1 = Conversation(
            user_id=user.id,
            trip_id=trip.id,
            title="Conversation 1",
        )
        conv2 = Conversation(
            user_id=user.id,
            trip_id=trip.id,
            title="Conversation 2",
        )
        db_session.add_all([conv1, conv2])
        await db_session.commit()

        # Query trip with conversations eager-loaded
        result = await db_session.execute(
            select(Trip)
            .where(Trip.id == trip.id)
            .options(selectinload(Trip.conversations))
        )
        loaded_trip = result.scalar_one_or_none()

        assert loaded_trip is not None
        assert len(loaded_trip.conversations) == 2
        conversation_ids = {c.id for c in loaded_trip.conversations}
        assert conv1.id in conversation_ids
        assert conv2.id in conversation_ids

    @pytest.mark.asyncio
    async def test_conversation_can_access_related_trip(self, db_session: AsyncSession):
        """Test that a Conversation can access its related trip via conv.trip"""
        user = _make_user(db_session, "convrel")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        conv = Conversation(
            user_id=user.id,
            trip_id=trip.id,
            title="Linked Conversation",
        )
        db_session.add(conv)
        await db_session.commit()

        # Query conversation with trip eager-loaded
        result = await db_session.execute(
            select(Conversation)
            .where(Conversation.id == conv.id)
            .options(selectinload(Conversation.trip))
        )
        loaded_conv = result.scalar_one_or_none()

        assert loaded_conv is not None
        assert loaded_conv.trip is not None
        assert loaded_conv.trip.id == trip.id
        assert loaded_conv.trip.city == "Shanghai"

    @pytest.mark.asyncio
    async def test_delete_trip_sets_trip_id_null(self, db_session: AsyncSession):
        """Test that deleting a trip sets trip_id to NULL on related conversations (ON DELETE SET NULL) (T4-AC2)"""
        user = _make_user(db_session, "delnull")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        conv1 = Conversation(
            user_id=user.id,
            trip_id=trip.id,
            title="Conv to keep 1",
        )
        conv2 = Conversation(
            user_id=user.id,
            trip_id=trip.id,
            title="Conv to keep 2",
        )
        db_session.add_all([conv1, conv2])
        await db_session.commit()

        # Verify conversations are linked before deletion
        assert conv1.trip_id == trip.id
        assert conv2.trip_id == trip.id

        # Delete the trip
        await db_session.delete(trip)
        await db_session.commit()

        # Verify conversations still exist but trip_id is NULL
        result1 = await db_session.execute(
            select(Conversation).where(Conversation.id == conv1.id)
        )
        loaded_conv1 = result1.scalar_one_or_none()

        result2 = await db_session.execute(
            select(Conversation).where(Conversation.id == conv2.id)
        )
        loaded_conv2 = result2.scalar_one_or_none()

        assert loaded_conv1 is not None, "Conversation should not be deleted"
        assert loaded_conv1.trip_id is None, "trip_id should be NULL after trip deletion"

        assert loaded_conv2 is not None, "Conversation should not be deleted"
        assert loaded_conv2.trip_id is None, "trip_id should be NULL after trip deletion"


class TestGetOrCreateConversationTripId:
    """Test cases for _get_or_create_conversation trip_id passthrough (T6)"""

    @staticmethod
    def _make_mock_session():
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        return mock_session

    @pytest.mark.asyncio
    async def test_create_conversation_with_trip_id(self, db_session: AsyncSession):
        """新建对话时写入 trip_id (T6-AC1)"""
        from src.services.trip_service import _get_or_create_conversation

        user = _make_user(db_session, "create_trip")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        mock_session = self._make_mock_session()

        with patch("src.services.trip_service.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_or_create_conversation(
                user_id=user.id,
                conversation_id=None,
                trip_id=trip.id,
            )

        # 验证：Conversation 被正确构造并传入 trip_id
        added_conv = mock_session.add.call_args[0][0]
        assert added_conv.user_id == user.id
        assert added_conv.title == "新对话"
        assert added_conv.trip_id == trip.id
        # 验证：commit + refresh 被调用
        mock_session.commit.assert_called()
        mock_session.refresh.assert_called()

    @pytest.mark.asyncio
    async def test_reuse_conversation_backfills_trip_id(self, db_session: AsyncSession):
        """复用已有对话时，若 trip_id 为 NULL 则回写 (T6-AC2)"""
        from src.services.trip_service import _get_or_create_conversation

        user = _make_user(db_session, "backfill_trip")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        # 创建无 trip_id 的对话（通过 db_session 直接写入测试库）
        existing_conv = Conversation(user_id=user.id, title="已有对话", trip_id=None)
        db_session.add(existing_conv)
        await db_session.commit()
        await db_session.refresh(existing_conv)

        assert existing_conv.trip_id is None

        mock_session = self._make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_conv
        mock_session.execute.return_value = mock_result

        with patch("src.services.trip_service.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_or_create_conversation(
                user_id=user.id,
                conversation_id=existing_conv.id,
                trip_id=trip.id,
            )

        # 验证：返回已有对话，且 trip_id 已被回写
        assert result.id == existing_conv.id
        assert result.trip_id == trip.id
        mock_session.commit.assert_called()
        mock_session.refresh.assert_called()

    @pytest.mark.asyncio
    async def test_reuse_conversation_preserves_existing_trip_id(self, db_session: AsyncSession):
        """复用已有对话时，若 trip_id 已存在则不变 (T6-AC3)"""
        from src.services.trip_service import _get_or_create_conversation

        user = _make_user(db_session, "preserve_trip")
        await db_session.commit()

        trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(trip)

        other_trip = _make_trip(db_session, user.id)
        await db_session.commit()
        await db_session.refresh(other_trip)

        # 创建已关联 trip1 的对话
        existing_conv = Conversation(user_id=user.id, title="已有对话", trip_id=trip.id)
        db_session.add(existing_conv)
        await db_session.commit()
        await db_session.refresh(existing_conv)

        assert existing_conv.trip_id == trip.id

        mock_session = self._make_mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_conv
        mock_session.execute.return_value = mock_result

        with patch("src.services.trip_service.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_or_create_conversation(
                user_id=user.id,
                conversation_id=existing_conv.id,
                trip_id=other_trip.id,
            )

        assert result.id == existing_conv.id
        assert result.trip_id == trip.id  # 未被覆盖
        # trip_id 已存在且一致，不触发 commit/refresh，直接返回
        mock_session.commit.assert_not_called()
        mock_session.refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_conversation_without_trip_id(self, db_session: AsyncSession):
        """新建对话时不传 trip_id → 保持 NULL (T6-AC4)"""
        from src.services.trip_service import _get_or_create_conversation

        user = _make_user(db_session, "no_trip")
        await db_session.commit()

        mock_session = self._make_mock_session()

        with patch("src.services.trip_service.async_session") as mock_session_ctx:
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _get_or_create_conversation(
                user_id=user.id,
                conversation_id=None,
                trip_id=None,
            )

        added_conv = mock_session.add.call_args[0][0]
        assert added_conv.user_id == user.id
        assert added_conv.title == "新对话"
        assert added_conv.trip_id is None
        mock_session.commit.assert_called()
        mock_session.refresh.assert_called()
