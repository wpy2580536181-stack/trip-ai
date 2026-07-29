"""Fix 1 链路测试：trigger_modify → 结构化 trip_modified SSE 事件

覆盖：
- ChatAgent._escalate_modify：成功发出 trip_modified 事件、返回纯文本摘要
- TripService.chat_stream：trip_modified 事件透传且先于 complete；落库内容为摘要文本
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.agent.agents.chat_agent import ChatAgent
from src.services.agent.schemas import PlanResult
from src.services.trip_service import TripService


FAKE_PLAN = {
    "city": "北京",
    "days": 3,
    "dailyItinerary": [],
    "budgetBreakdown": {},
}

FAKE_META = {
    "trip_id": 1,
    "user_id": 7,
    "city": "北京",
    "days": 3,
    "budget": 5000,
    "departure_city": None,
    "content": {"city": "北京", "days": 3},
}


def _make_agent(on_event=None) -> ChatAgent:
    return ChatAgent(llm=MagicMock(), on_event=on_event, system_prompt="test")


# ===========================================================================
# ChatAgent._escalate_modify
# ===========================================================================


class TestEscalateModify:

    @pytest.mark.asyncio
    async def test_success_emits_trip_modified_event(self):
        """成功：发一次 trip_modified 事件（newTripId/parentTripId/summary），返回纯文本"""
        events = []

        async def on_event(e):
            events.append(e)

        agent = _make_agent(on_event=on_event)
        agent._trip_meta = dict(FAKE_META)

        mock_orch = MagicMock()
        mock_orch.modify = AsyncMock(return_value=PlanResult(plan=FAKE_PLAN))

        with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock, return_value=99):
            result = await agent._escalate_modify({"modify_request": "换掉第2天下午的景点"})

        # 返回值为人类可读文本，不再是裸 JSON
        assert isinstance(result, str)
        assert '"type"' not in result
        assert "修改版行程" in result

        # 恰好一次结构化事件
        modified = [e for e in events if e.get("type") == "trip_modified"]
        assert len(modified) == 1
        data = modified[0]["data"]
        assert data["newTripId"] == 99
        assert data["parentTripId"] == FAKE_META["trip_id"]
        assert data["summary"] == result

    @pytest.mark.asyncio
    async def test_no_trip_meta_returns_hint_without_event(self):
        """无 trip_meta：返回提示文本，不发事件"""
        events = []

        async def on_event(e):
            events.append(e)

        agent = _make_agent(on_event=on_event)
        agent._trip_meta = None

        result = await agent._escalate_modify({"modify_request": "改行程"})

        assert "没有关联行程" in result
        assert events == []

    @pytest.mark.asyncio
    async def test_modify_failure_no_event(self):
        """Orchestrator 返回空 plan：返回失败文本，不发事件"""
        events = []

        async def on_event(e):
            events.append(e)

        agent = _make_agent(on_event=on_event)
        agent._trip_meta = dict(FAKE_META)

        mock_orch = MagicMock()
        mock_orch.modify = AsyncMock(return_value=PlanResult(plan=None, error="LLM 输出解析失败"))

        with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch):
            result = await agent._escalate_modify({"modify_request": "改行程"})

        assert "修改失败" in result
        assert events == []

    @pytest.mark.asyncio
    async def test_success_without_on_event(self):
        """on_event 为 None：不崩溃，仍返回摘要文本"""
        agent = _make_agent(on_event=None)
        agent._trip_meta = dict(FAKE_META)

        mock_orch = MagicMock()
        mock_orch.modify = AsyncMock(return_value=PlanResult(plan=FAKE_PLAN))

        with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock, return_value=100):
            result = await agent._escalate_modify({"modify_request": "改行程"})

        assert "修改版行程" in result


# ===========================================================================
# TripService.chat_stream 透传
# ===========================================================================


class TestChatStreamTripModified:

    @pytest.mark.asyncio
    async def test_trip_modified_passthrough_before_complete(self):
        """Agent 发 trip_modified → SSE 输出含该事件且先于 complete；落库为摘要文本"""
        from src.models.conversation import Conversation

        svc = TripService()
        mock_conv = Conversation(id=42, user_id=1, title="新对话")
        summary = "已按您的要求生成修改版行程：北京3日游，页面将自动切换到新版本。"

        with patch("src.services.trip_service._get_or_create_conversation", new_callable=AsyncMock, return_value=mock_conv), \
             patch("src.services.trip_service._save_message", new_callable=AsyncMock, return_value=1), \
             patch("src.services.trip_service._update_message", new_callable=AsyncMock) as mock_update, \
             patch("src.services.trip_service.get_agent_engine") as mock_get_engine, \
             patch.object(TripService, "_post_chat_tasks", new_callable=AsyncMock), \
             patch("src.services.trip_service.trip_log"):

            async def fake_chat(*args, on_event=None, **kwargs):
                await on_event({
                    "type": "trip_modified",
                    "data": {"newTripId": 99, "parentTripId": 1, "summary": summary},
                })
                await on_event({"type": "complete", "content": summary, "usage": {"total": 10}})

            mock_engine = MagicMock()
            mock_engine.chat = fake_chat
            mock_get_engine.return_value = mock_engine

            events = []
            async for event in svc.chat_stream(user_id=1, message="帮我修改行程"):
                events.append(event)

        event_types = [e.get("type") for e in events]
        assert "trip_modified" in event_types
        assert "complete" in event_types
        # 事件顺序：trip_modified 先于 complete
        assert event_types.index("trip_modified") < event_types.index("complete")

        # 事件数据完整透传
        tm = next(e for e in events if e.get("type") == "trip_modified")
        assert tm["data"]["newTripId"] == 99
        assert tm["data"]["parentTripId"] == 1

        # complete 事件不含 plan 内容（协议层分离）
        complete = next(e for e in events if e.get("type") == "complete")
        assert set(complete["data"].keys()) == {"conversationId", "usage"}

        # 落库 assistant 消息为摘要文本（非 JSON）
        persisted_contents = [c.args[1] for c in mock_update.await_args_list]
        assert summary in persisted_contents
