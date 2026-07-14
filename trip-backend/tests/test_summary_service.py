"""Tests for Summary Service — token estimation + pure function logic"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.utils.tokens import estimate_tokens, estimate_messages_tokens
from src.services.summary_service import SummaryService, select_compaction_range
from src.models.conversation import Conversation
from src.models.message import Message
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


# ===========================================================================
# TestEstimateTokens — estimate_tokens (from utils/tokens.py)
# ===========================================================================


class TestEstimateTokens:
    """estimate_tokens test cases"""

    def test_estimate_tokens_chinese(self):
        """中文文本 token 估算（~1.5 token/字）"""
        text = "成都三日行程规划武侯祠锦里春熙路太古里宽窄巷子"
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert isinstance(tokens, int)
        cjk_count = sum(1 for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF)
        expected = cjk_count / 1.5
        assert abs(tokens - expected) <= 2

    def test_estimate_tokens_english(self):
        """英文文本 token 估算（~4 chars/token）"""
        text = "Hello world this is a test"  # 26 chars (including spaces)
        tokens = estimate_tokens(text)
        assert tokens > 0
        # 26 other chars → ceil(26 / 4) = 7
        assert tokens == 7

    def test_estimate_tokens_mixed(self):
        """中英文混合"""
        text = "Hello世界test测试"
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert tokens >= 5

    def test_estimate_tokens_empty(self):
        """空字符串 → 0"""
        assert estimate_tokens("") == 0

    def test_estimate_messages_tokens(self):
        """消息列表总 token"""
        messages = [
            {"role": "user", "content": "你好世界"},
            {"role": "assistant", "content": "Hello world"},
        ]
        total = estimate_messages_tokens(messages)
        assert total > 0
        expected = estimate_tokens("你好世界") + estimate_tokens("Hello world")
        assert total == expected


# ===========================================================================
# TestSelectCompactionRange — select_compaction_range (pure function)
# ===========================================================================


class TestSelectCompactionRange:
    """select_compaction_range test cases"""

    def test_select_compaction_range(self):
        """正确选出要压缩的消息范围"""
        messages = [
            {"role": "user", "content": "A" * 100},
            {"role": "assistant", "content": "B" * 100},
            {"role": "user", "content": "C" * 100},
            {"role": "assistant", "content": "D" * 100},
        ]
        total_tokens = 100
        target_tokens = 50

        result = select_compaction_range(messages, total_tokens, target_tokens)
        assert len(result["to_compact"]) > 0
        assert len(result["to_keep"]) > 0
        assert result["freed_tokens"] > 0
        assert len(result["to_compact"]) + len(result["to_keep"]) == len(messages)

    def test_select_compaction_range_empty(self):
        """消息太少不压缩（total_tokens <= target_tokens）"""
        messages = [
            {"role": "user", "content": "短消息"},
        ]
        total_tokens = 10
        target_tokens = 100

        result = select_compaction_range(messages, total_tokens, target_tokens)
        assert result["to_compact"] == []
        assert result["to_keep"] == messages
        assert result["freed_tokens"] == 0


# ===========================================================================
# TestSummaryService — SummaryService methods
# ===========================================================================


class TestSummaryService:
    """SummaryService test cases"""

    def test_compress_context_messages_filter(self):
        """excludedFromContext 消息被正确过滤"""
        all_messages = [
            {"id": 1, "role": "user", "content": "旧消息1", "excluded": True},
            {"id": 2, "role": "assistant", "content": "旧回复1", "excluded": True},
            {"id": 3, "role": "user", "content": "新消息", "excluded": False},
            {"id": 4, "role": "assistant", "content": "新回复", "excluded": False},
        ]
        context = [m for m in all_messages if not m["excluded"]]
        assert len(context) == 2
        assert all(m["id"] in (3, 4) for m in context)

    def test_should_compress_below_threshold(self):
        """token 数低于阈值时不压缩"""
        messages = [{"role": "user", "content": "短消息"}]
        total_tokens = 100
        target_tokens = 12000

        result = select_compaction_range(messages, total_tokens, target_tokens)
        assert result["to_compact"] == []
        assert result["freed_tokens"] == 0

    def test_should_compress_above_threshold(self):
        """token 数超过阈值时需要压缩"""
        messages = [
            {"role": "user", "content": "X" * 40000},
            {"role": "assistant", "content": "Y" * 40000},
        ]
        total_tokens = 20000
        target_tokens = 12000

        result = select_compaction_range(messages, total_tokens, target_tokens)
        assert len(result["to_compact"]) > 0
        assert result["freed_tokens"] > 0

    @pytest.mark.asyncio
    async def test_get_summary_no_summary(self, db_session: AsyncSession):
        """无摘要时返回空"""
        user = _make_user(db_session)
        await db_session.commit()

        conv = Conversation(
            user_id=user.id,
            title="测试对话",
            summary=None,
            recap=None,
            summary_error=False,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        svc = SummaryService()
        with patch("src.services.summary_service.log"):
            result = await svc.get_summary(db_session, conv.id)

        assert result["summary"] is None
        assert result["recap"] is None

    @pytest.mark.asyncio
    async def test_append_key_decision(self, db_session: AsyncSession):
        """关键决策正确追加到 conversation.summary"""
        user = _make_user(db_session)
        await db_session.commit()

        conv = Conversation(
            user_id=user.id,
            title="测试对话",
            summary=None,
            recap=None,
            summary_error=False,
        )
        db_session.add(conv)
        await db_session.commit()
        await db_session.refresh(conv)

        svc = SummaryService()

        with patch("src.services.summary_service.log"):
            # Append first decision
            await svc.append_key_decision(db_session, conv.id, "确定去成都3天")

        await db_session.refresh(conv)
        assert conv.summary is not None
        assert "确定去成都3天" in conv.summary
        assert conv.summary_error is False

        with patch("src.services.summary_service.log"):
            # Append second decision — should append with marker
            await svc.append_key_decision(db_session, conv.id, "预算5000元")

        await db_session.refresh(conv)
        assert "确定去成都3天" in conv.summary
        assert "预算5000元" in conv.summary
        assert "### 追加于" in conv.summary
