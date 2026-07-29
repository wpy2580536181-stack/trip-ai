"""Fix 1/2 链路测试：trigger_modify → 结构化 trip_modified SSE 事件 + usage 合并

覆盖：
- ChatAgent._escalate_modify：成功发出 trip_modified 事件、返回纯文本摘要 + usage
- ChatAgent.run：升级路径 usage 与 chat LLM usage 合并（Fix 2）
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
        mock_orch.modify = AsyncMock(return_value=PlanResult(
            plan=FAKE_PLAN,
            usage={"prompt": 800, "completion": 200, "total": 1000, "cached": 0},
        ))

        with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock, return_value=99):
            result, usage = await agent._escalate_modify({"modify_request": "换掉第2天下午的景点"})

        # 返回值为人类可读文本，不再是裸 JSON；usage 透传 Orchestrator 汇总
        assert isinstance(result, str)
        assert '"type"' not in result
        assert "修改版行程" in result
        assert usage["total"] == 1000

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

        result, usage = await agent._escalate_modify({"modify_request": "改行程"})

        assert "没有关联行程" in result
        assert usage == {}
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
            result, _usage = await agent._escalate_modify({"modify_request": "改行程"})

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
            result, _usage = await agent._escalate_modify({"modify_request": "改行程"})

        assert "修改版行程" in result


# ===========================================================================
# Fix 2：ChatAgent.run 的 usage 合并
# ===========================================================================


class TestRunUsageMerge:

    @pytest.mark.asyncio
    async def test_modify_usage_merged_into_output(self):
        """chat LLM usage + Orchestrator.modify usage 合并进 AgentOutput.usage"""
        agent = _make_agent()

        raw_msg = MagicMock()
        raw_msg.tool_calls = [{"name": "trigger_modify", "args": {"modify_request": "改"}}]

        with patch.object(agent, "_get_tools", new_callable=AsyncMock, return_value=[]), \
             patch.object(
                 agent, "_stream_llm", new_callable=AsyncMock,
                 return_value=("", {"prompt": 80, "completion": 20, "total": 100, "cached": 0}, raw_msg),
             ), \
             patch.object(
                 agent, "_escalate_modify", new_callable=AsyncMock,
                 return_value=("已修改", {"prompt": 800, "completion": 200, "total": 1000, "cached": 5}),
             ):
            output = await agent.run(message="改行程", trip_meta=dict(FAKE_META))

        assert output.result == "已修改"
        assert output.usage == {"prompt": 880, "completion": 220, "total": 1100, "cached": 5}

    @pytest.mark.asyncio
    async def test_plan_usage_merged_into_output(self):
        """trigger_plan 路径同样合并 usage"""
        agent = _make_agent()

        raw_msg = MagicMock()
        raw_msg.tool_calls = [{"name": "trigger_plan", "args": {"city": "北京", "days": 3, "budget": 5000}}]

        with patch.object(agent, "_get_tools", new_callable=AsyncMock, return_value=[]), \
             patch.object(
                 agent, "_stream_llm", new_callable=AsyncMock,
                 return_value=("", {"prompt": 10, "completion": 5, "total": 15, "cached": 0}, raw_msg),
             ), \
             patch.object(
                 agent, "_escalate_plan", new_callable=AsyncMock,
                 return_value=("{\"city\": \"北京\"}", {"prompt": 100, "completion": 50, "total": 150, "cached": 0}),
             ):
            output = await agent.run(message="规划北京3日游")

        assert output.usage["total"] == 165

    @pytest.mark.asyncio
    async def test_no_tool_call_usage_unchanged(self):
        """无 tool_call：usage 保持 chat LLM 原值"""
        agent = _make_agent()

        raw_msg = MagicMock()
        raw_msg.tool_calls = []

        with patch.object(agent, "_get_tools", new_callable=AsyncMock, return_value=[]), \
             patch.object(
                 agent, "_stream_llm", new_callable=AsyncMock,
                 return_value=("你好", {"prompt": 10, "completion": 5, "total": 15, "cached": 0}, raw_msg),
             ):
            output = await agent.run(message="你好")

        assert output.result == "你好"
        assert output.usage["total"] == 15


# ===========================================================================
# Fix 7：ChatAgent._escalate_plan（对话内全量规划落库）
# ===========================================================================


class TestEscalatePlan:

    @pytest.mark.asyncio
    async def test_plan_persists_and_emits_trip_planned(self):
        """有效 user_id：落库 + 发 trip_planned 事件 + 返回文本摘要"""
        events = []

        async def on_event(e):
            events.append(e)

        agent = _make_agent(on_event=on_event)
        agent._user_id = 7

        mock_orch = MagicMock()
        mock_orch.plan = AsyncMock(return_value=PlanResult(
            plan=FAKE_PLAN,
            usage={"prompt": 500, "completion": 100, "total": 600, "cached": 0},
        ))

        with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock, return_value=88) as mock_persist:
            result, usage = await agent._escalate_plan({"city": "北京", "days": 3, "budget": 5000})

        # 落库参数：真实 user_id、无父版本
        mock_persist.assert_awaited_once()
        kwargs = mock_persist.await_args.kwargs
        assert kwargs["user_id"] == 7
        assert kwargs["parent_trip_id"] is None

        # 返回文本摘要（非 JSON）+ usage 透传
        assert '"type"' not in result
        assert "已为您规划" in result
        assert usage["total"] == 600

        # trip_planned 事件
        planned = [e for e in events if e.get("type") == "trip_planned"]
        assert len(planned) == 1
        assert planned[0]["data"]["newTripId"] == 88

    @pytest.mark.asyncio
    async def test_plan_without_user_id_no_persist(self):
        """user_id=0（防御）：不落库、不发事件"""
        events = []

        async def on_event(e):
            events.append(e)

        agent = _make_agent(on_event=on_event)
        agent._user_id = 0

        mock_orch = MagicMock()
        mock_orch.plan = AsyncMock(return_value=PlanResult(plan=FAKE_PLAN))

        with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock) as mock_persist:
            result, _usage = await agent._escalate_plan({"city": "北京", "days": 3, "budget": 5000})

        mock_persist.assert_not_awaited()
        assert events == []
        assert result  # 仍有回复内容

    @pytest.mark.asyncio
    async def test_run_passes_user_id(self):
        """run(user_id=...) → 存入 self._user_id 供升级路径使用"""
        agent = _make_agent()

        raw_msg = MagicMock()
        raw_msg.tool_calls = []

        with patch.object(agent, "_get_tools", new_callable=AsyncMock, return_value=[]), \
             patch.object(
                 agent, "_stream_llm", new_callable=AsyncMock,
                 return_value=("你好", {"prompt": 1, "completion": 1, "total": 2, "cached": 0}, raw_msg),
             ):
            await agent.run(message="你好", user_id=42)

        assert agent._user_id == 42


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

    @pytest.mark.asyncio
    async def test_full_event_sequence(self):
        """链路回归：chunk → tool_start/tool_end → trip_modified → complete 顺序完整"""
        from src.models.conversation import Conversation

        svc = TripService()
        mock_conv = Conversation(id=42, user_id=1, title="新对话")

        with patch("src.services.trip_service._get_or_create_conversation", new_callable=AsyncMock, return_value=mock_conv), \
             patch("src.services.trip_service._save_message", new_callable=AsyncMock, return_value=1), \
             patch("src.services.trip_service._update_message", new_callable=AsyncMock), \
             patch("src.services.trip_service.get_agent_engine") as mock_get_engine, \
             patch.object(TripService, "_post_chat_tasks", new_callable=AsyncMock), \
             patch("src.services.trip_service.trip_log"):

            async def fake_chat(*args, on_event=None, **kwargs):
                await on_event({"type": "chunk", "content": "好的，"})
                await on_event({"type": "tool_start", "name": "search_spots"})
                await on_event({"type": "tool_end", "name": "search_spots"})
                await on_event({"type": "trip_modified", "data": {"newTripId": 99}})
                await on_event({"type": "complete", "content": "已修改", "usage": {"total": 10}})

            mock_engine = MagicMock()
            mock_engine.chat = fake_chat
            mock_get_engine.return_value = mock_engine

            events = []
            async for event in svc.chat_stream(user_id=1, message="帮我修改行程"):
                events.append(event)

        event_types = [e.get("type") for e in events if e.get("type") != "heartbeat"]
        assert event_types == ["chunk", "tool_start", "tool_end", "trip_modified", "complete"]
