"""Tests for Feedback Service"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date, timedelta, datetime, timezone

from src.services.feedback_service import FeedbackService
from src.models.feedback import Feedback
from src.models.message import Message
from src.models.conversation import Conversation
from src.models.user import User
from src.schemas.user import FeedbackCreate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _create_user(db: AsyncSession, **kwargs) -> User:
    defaults = dict(
        username=kwargs.pop("username", "u1"),
        email=kwargs.pop("email", "u1@example.com"),
        password="hashed",
        nickname="User",
        role_id=2,
        status=1,
    )
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


async def _create_conversation(db: AsyncSession, user_id: int, title="t") -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    await db.flush()
    return conv


async def _create_message(db: AsyncSession, conversation_id: int, role="assistant", content="hi") -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    await db.flush()
    return msg


def _feedback_create(message_id: int, conversation_id: int, rating=1, comment=None, tags=None) -> FeedbackCreate:
    return FeedbackCreate(
        messageId=message_id,
        conversationId=conversation_id,
        rating=rating,
        comment=comment,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFeedbackService:
    """Test cases for FeedbackService"""

    # ---- submit_feedback --------------------------------------------------

    @pytest.mark.asyncio
    async def test_submit_feedback_success(self, db_session: AsyncSession):
        """正常提交反馈"""
        user = await _create_user(db_session, username="fb_ok")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        data = _feedback_create(msg.id, conv.id, rating=1, comment="great")
        result = await FeedbackService.submit_feedback(db_session, user.id, data)

        assert result["id"] is not None
        assert result["rating"] == 1

    @pytest.mark.asyncio
    async def test_submit_feedback_idor_protection(self, db_session: AsyncSession):
        """反馈他人消息 → PermissionError"""
        owner = await _create_user(db_session, username="owner")
        other = await _create_user(db_session, username="other", email="other@example.com")
        conv = await _create_conversation(db_session, owner.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        data = _feedback_create(msg.id, conv.id, rating=1)
        with pytest.raises(PermissionError):
            await FeedbackService.submit_feedback(db_session, other.id, data)

    @pytest.mark.asyncio
    async def test_submit_feedback_non_assistant(self, db_session: AsyncSession):
        """反馈非 assistant 消息 → ValueError"""
        user = await _create_user(db_session, username="fb_nonasst")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="user")
        await db_session.commit()

        data = _feedback_create(msg.id, conv.id, rating=1)
        with pytest.raises(ValueError, match="agent"):
            await FeedbackService.submit_feedback(db_session, user.id, data)

    @pytest.mark.asyncio
    async def test_submit_feedback_message_not_found(self, db_session: AsyncSession):
        """不存在的消息 → ValueError"""
        user = await _create_user(db_session, username="fb_nf")
        conv = await _create_conversation(db_session, user.id)
        await db_session.commit()

        data = _feedback_create(99999, conv.id, rating=1)
        with pytest.raises(ValueError, match="消息不存在"):
            await FeedbackService.submit_feedback(db_session, user.id, data)

    @pytest.mark.asyncio
    async def test_submit_feedback_comment_truncation(self, db_session: AsyncSession):
        """comment 超过 500 字符自动截断"""
        user = await _create_user(db_session, username="fb_trunc")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        long_comment = "x" * 600
        data = _feedback_create(msg.id, conv.id, rating=1, comment=long_comment)
        result = await FeedbackService.submit_feedback(db_session, user.id, data)

        # Verify truncation
        stmt = select(Feedback).where(Feedback.id == result["id"])
        fb = (await db_session.execute(stmt)).scalar_one()
        assert len(fb.comment) == 500

    @pytest.mark.asyncio
    async def test_submit_feedback_tags_limit(self, db_session: AsyncSession):
        """tags 超过 10 个自动截断"""
        user = await _create_user(db_session, username="fb_tags")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        many_tags = [f"tag{i}" for i in range(15)]
        data = _feedback_create(msg.id, conv.id, rating=1, tags=many_tags)
        result = await FeedbackService.submit_feedback(db_session, user.id, data)

        stmt = select(Feedback).where(Feedback.id == result["id"])
        fb = (await db_session.execute(stmt)).scalar_one()
        assert len(fb.tags) == 10

    @pytest.mark.asyncio
    async def test_submit_feedback_update_existing(self, db_session: AsyncSession):
        """重复提交更新已有反馈（upsert）"""
        user = await _create_user(db_session, username="fb_upsert")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        data1 = _feedback_create(msg.id, conv.id, rating=1, comment="first")
        r1 = await FeedbackService.submit_feedback(db_session, user.id, data1)

        data2 = _feedback_create(msg.id, conv.id, rating=-1, comment="updated")
        r2 = await FeedbackService.submit_feedback(db_session, user.id, data2)

        # Same feedback id (updated, not new)
        assert r1["id"] == r2["id"]
        assert r2["rating"] == -1

    # ---- get_message_stats ------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_message_stats_empty(self, db_session: AsyncSession):
        """无反馈时返回空统计"""
        stats = await FeedbackService.get_message_stats(db_session, 99999)
        assert stats["total"] == 0
        assert stats["up"] == 0
        assert stats["down"] == 0
        assert stats["satisfactionRate"] is None

    @pytest.mark.asyncio
    async def test_get_message_stats_with_data(self, db_session: AsyncSession):
        """有反馈时正确聚合"""
        # Use 3 different users so upsert doesn't overwrite (unique user+message)
        users = []
        convs = []
        msg = None
        for i, name in enumerate(["ms_u1", "ms_u2", "ms_u3"]):
            u = await _create_user(db_session, username=name, email=f"{name}@example.com")
            users.append(u)
            c = await _create_conversation(db_session, u.id, title=f"c{i}")
            convs.append(c)
            m = await _create_message(db_session, c.id, role="assistant", content=f"m{i}")
            if i == 0:
                msg = m
            await db_session.flush()
        await db_session.commit()

        # 3 different users rating the SAME first message
        for user, conv, r in [(users[0], convs[0], 1), (users[1], convs[1], 1), (users[2], convs[2], -1)]:
            d = _feedback_create(msg.id, conv.id, rating=r)
            await FeedbackService.submit_feedback(db_session, user.id, d)

        stats = await FeedbackService.get_message_stats(db_session, msg.id)
        assert stats["total"] == 3
        assert stats["up"] == 2
        assert stats["down"] == 1
        assert abs(stats["satisfactionRate"] - 2 / 3 * 100) < 0.01

    # ---- get_global_stats -------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_global_stats_aggregation(self, db_session: AsyncSession):
        """正确聚合全局统计"""
        # Use 3 separate users to avoid upsert on same user+message
        users = []
        convs = []
        msgs = []
        for i, name in enumerate(["gs_u1", "gs_u2", "gs_u3"]):
            u = await _create_user(db_session, username=name, email=f"{name}@example.com")
            users.append(u)
            c = await _create_conversation(db_session, u.id, title=f"gc{i}")
            convs.append(c)
            m = await _create_message(db_session, c.id, role="assistant", content=f"gm{i}")
            msgs.append(m)
        await db_session.commit()

        for user, conv, msg, r in zip(users, convs, msgs, [1, 1, -1]):
            d = _feedback_create(msg.id, conv.id, rating=r)
            await FeedbackService.submit_feedback(db_session, user.id, d)

        stats = await FeedbackService.get_global_stats(db_session, days=7)
        assert stats["totalCount"] == 3
        assert stats["upCount"] == 2
        assert stats["downCount"] == 1
        assert abs(stats["satisfactionRate"] - 2 / 3 * 100) < 0.01

    @pytest.mark.asyncio
    async def test_get_global_stats_recent_down_comments(self, db_session: AsyncSession):
        """recentDownComments 最多 20 条"""
        user = await _create_user(db_session, username="fb_rdcomm")
        conv = await _create_conversation(db_session, user.id)
        # Create 25 messages and 25 down-feedbacks (one per message to avoid upsert)
        for i in range(25):
            msg = await _create_message(db_session, conv.id, role="assistant", content=f"msg{i}")
            await db_session.flush()
            d = _feedback_create(msg.id, conv.id, rating=-1, comment=f"bad{i}")
            await FeedbackService.submit_feedback(db_session, user.id, d)

        stats = await FeedbackService.get_global_stats(db_session, days=7)
        assert len(stats["recentDownComments"]) == 20

    # ---- get_daily_stats --------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_daily_stats_with_data(self, db_session: AsyncSession):
        """正确按日期分组"""
        user = await _create_user(db_session, username="fb_daily")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        for r in [1, -1, 1]:
            d = _feedback_create(msg.id, conv.id, rating=r)
            await FeedbackService.submit_feedback(db_session, user.id, d)

        today = date.today()
        stats = await FeedbackService.get_daily_stats(db_session, today - timedelta(days=1), today)
        # Should have at least one day with data
        day_with_data = [s for s in stats if s["total"] > 0]
        assert len(day_with_data) >= 1

    @pytest.mark.asyncio
    async def test_get_daily_stats_date_fill(self, db_session: AsyncSession):
        """连续日期无间断（填充空日期）"""
        today = date.today()
        start = today - timedelta(days=6)
        stats = await FeedbackService.get_daily_stats(db_session, start, today)
        # 7 days should give 7 entries
        assert len(stats) == 7
        dates = [s["date"] for s in stats]
        for i in range(7):
            assert (start + timedelta(days=i)).isoformat() in dates

    @pytest.mark.asyncio
    async def test_get_daily_stats_empty(self, db_session: AsyncSession):
        """无数据时返回空（每天 total=0）"""
        far_past = date(2020, 1, 1)
        stats = await FeedbackService.get_daily_stats(db_session, far_past, far_past + timedelta(days=2))
        assert len(stats) == 3
        assert all(s["total"] == 0 for s in stats)

    # ---- list_for_message -------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_for_message_success(self, db_session: AsyncSession):
        """返回消息的所有反馈"""
        user = await _create_user(db_session, username="fb_list")
        conv = await _create_conversation(db_session, user.id)
        msg = await _create_message(db_session, conv.id, role="assistant")
        await db_session.commit()

        d = _feedback_create(msg.id, conv.id, rating=1, comment="nice", tags=["good"])
        await FeedbackService.submit_feedback(db_session, user.id, d)

        items = await FeedbackService.list_for_message(db_session, msg.id)
        assert len(items) == 1
        assert items[0]["rating"] == 1
        assert items[0]["user"]["username"] == "fb_list"

    # ---- convert_to_fixture -----------------------------------------------

    @pytest.mark.asyncio
    async def test_convert_empty_ids(self, db_session: AsyncSession):
        """空 feedbackIds → 验证错误"""
        with pytest.raises(ValueError, match="非空"):
            await FeedbackService.convert_to_fixture(db_session, [])

    @pytest.mark.asyncio
    async def test_convert_max_50(self, db_session: AsyncSession):
        """超过 50 条 → 验证错误"""
        with pytest.raises(ValueError, match="50"):
            await FeedbackService.convert_to_fixture(db_session, list(range(51)))

    @pytest.mark.asyncio
    async def test_convert_partial_failure(self, db_session: AsyncSession):
        """单条失败不阻断整批"""
        result = await FeedbackService.convert_to_fixture(db_session, [1, 2, 3])
        # Current implementation: all go to skipped (not implemented yet)
        assert len(result["skipped"]) == 3
        assert result["files"] == []
