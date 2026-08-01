"""E2E 风格测试：ChatAgent 需求补全（模拟 trip_service 层）。

不依赖外部服务，通过 patch 隔离数据库/LLM/Redis，
直接验证 _escalate_plan 的拦截逻辑 + SSE 事件格式。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.agent.agents.chat_agent import ChatAgent
from src.services.agent.agents.base_agent import AgentOutput


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make_agent(on_event=None) -> ChatAgent:
    """构建最小 ChatAgent（Mock LLM）。"""
    llm = MagicMock()
    agent = ChatAgent(llm=llm, on_event=on_event, user_id=1)
    agent.tools = []
    return agent


async def _fake_stream(**kwargs):
    """假 trip_service.chat_stream，返回简单事件。"""
    yield {"type": "delta", "data": "你好"}
    yield {"type": "complete", "data": {"conversationId": 1, "usage": {}}}


def _parse_events(raw_events: list[dict]) -> list[dict]:
    """从 SSE 行解析事件。"""
    events = []
    for line in raw_events:
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ---------------------------------------------------------------------------
# 场景 1：输入不完整 → 应发出 clarify card
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_1_incomplete_input_emits_clarify():
    """场景 1："周末想出去逛逛" → 返回 clarify card，不触发 Orchestrator。"""
    on_event = AsyncMock()
    agent = _make_agent(on_event=on_event)

    # LLM 返回空的 trigger_plan（无 city/days/budget）
    llm_return = AgentOutput(
        agent_name="chat",
        result="",
        usage={"prompt": 0, "completion": 0, "total": 0, "cached": 0},
        duration_ms=100,
    )
    with patch.object(ChatAgent, "_stream_llm", return_value=("", {}, MagicMock())):
        with patch.object(ChatAgent, "_execute_tool_card", return_value=None):
            # 模拟 LLM 返回 trigger_plan tool_call（空 args）
            raw_msg = MagicMock()
            raw_msg.tool_calls = [{"name": "trigger_plan", "args": {}}]
            with patch.object(ChatAgent, "_stream_llm", return_value=("", {}, raw_msg)):
                result = await agent.run(message="周末想出去逛逛")

    # 断言：发出 clarify card
    calls = [c[0][0] for c in on_event.call_args_list]
    clarify_events = [c for c in calls if c.get("card_type") == "clarify"]
    assert len(clarify_events) >= 1, f"应发出 clarify card，实际事件: {calls}"

    clarify_data = clarify_events[0]["data"]
    assert "fields" in clarify_data
    field_keys = {f["key"] for f in clarify_data["fields"]}
    assert {"city", "days", "budget"}.issubset(field_keys), f"缺少必填字段: {field_keys}"

    # 断言：未触发 Orchestrator（无 trip_planned 事件）
    trip_events = [c for c in calls if c.get("type") == "trip_planned"]
    assert len(trip_events) == 0, "未补全时应不触发 Orchestrator"


# ---------------------------------------------------------------------------
# 场景 2：补全后 → 应进入规划
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_2_complete_fields_triggers_orchestrator():
    """场景 2：补全"北京,2天,3000元" → 应触发 Orchestrator.plan()。"""
    on_event = AsyncMock()
    agent = _make_agent(on_event=on_event)

    args = {"city": "北京", "days": 2, "budget": 3000}

    # patch Orchestrator + TripService
    mock_orch = MagicMock()
    mock_result = MagicMock()
    mock_result.plan = {"city": "北京", "days": 2, "totalBudget": 3000}
    mock_result.usage = {"prompt": 100, "completion": 200, "total": 300, "cached": 0}
    mock_result.raw_output = '{"city":"北京"}'
    mock_orch.plan = AsyncMock(return_value=mock_result)

    with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch), \
         patch("src.services.trip_service.TripService._persist_trip", return_value=123):
        text, usage = await agent._escalate_plan(args)

    # 断言：发出 trip_planned（而非 clarify）
    calls = [c[0][0] for c in on_event.call_args_list]
    trip_events = [c for c in calls if c.get("type") == "trip_planned"]
    assert len(trip_events) >= 1, f"应触发 Orchestrator，实际事件: {calls}"

    # 断言：未发出 clarify
    clarify_events = [c for c in calls if c.get("card_type") == "clarify"]
    assert len(clarify_events) == 0, "完整 args 时不应发出 clarify card"


# ---------------------------------------------------------------------------
# 场景 3：完整输入 → 直接规划
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_3_full_input_no_clarify():
    """场景 3：完整输入"去成都玩3天，预算4000" → 直接规划，无 clarify。"""
    on_event = AsyncMock()
    agent = _make_agent(on_event=on_event)

    # 模拟 LLM 正确提取 args
    args = {"city": "成都", "days": 3, "budget": 4000}

    mock_orch = MagicMock()
    mock_result = MagicMock()
    mock_result.plan = {"city": "成都", "days": 3, "totalBudget": 4000}
    mock_result.usage = {"prompt": 100, "completion": 200, "total": 300, "cached": 0}
    mock_result.raw_output = '{"city":"成都"}'
    mock_orch.plan = AsyncMock(return_value=mock_result)

    with patch("src.services.agent.orchestrator.Orchestrator", return_value=mock_orch):
        text, usage = await agent._escalate_plan(args)

    calls = [c[0][0] for c in on_event.call_args_list]
    assert not any(c.get("card_type") == "clarify" for c in calls), \
        f"完整输入不应发出 clarify，实际: {calls}"


# ---------------------------------------------------------------------------
# 边界：departure_city 不影响完整性
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_departure_city_is_optional():
    """出发城市不影响完整性检查。"""
    args = {"city": "北京", "days": 2, "budget": 3000}
    # 即使有 departure_city，也不影响
    missing, _ = __import__("src.services.agent.intent", fromlist=["check_completeness"]).check_completeness(
        {**args, "departure_city": "上海"}
    )
    assert missing == []


# ---------------------------------------------------------------------------
# 边界：空 city 字符串 → 触发 clarify
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_city_triggers_clarify():
    on_event = AsyncMock()
    agent = _make_agent(on_event=on_event)

    args = {"city": "", "days": 2, "budget": 3000}
    text, _ = await agent._escalate_plan(args)

    calls = [c[0][0] for c in on_event.call_args_list]
    assert any(c.get("card_type") == "clarify" for c in calls), \
        f"空 city 应触发 clarify，实际: {calls}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
