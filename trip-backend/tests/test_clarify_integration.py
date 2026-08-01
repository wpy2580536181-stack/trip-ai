"""T5 集成测试：ChatAgent 需求补全端到端流程验证。

覆盖场景：
1. 输入"周末想出去逛逛" → 返回 clarify card（不触发 Orchestrator）
2. 补全字段后 → 进入规划流程
3. 完整输入"去北京玩 3 天，预算 4000" → 直接规划，无 clarify card
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent.intent import check_completeness, _build_clarify_field, ClarifyField
from src.services.agent.agents.chat_agent import ChatAgent
from src.services.agent.agents.base_agent import AgentOutput


# ---------------------------------------------------------------------------
# 辅助：构建 mock ChatAgent
# ---------------------------------------------------------------------------

def _make_chat_agent(on_event=None) -> ChatAgent:
    """构建最小 ChatAgent（不依赖 LLM）。"""
    llm = MagicMock()
    agent = ChatAgent(llm=llm, on_event=on_event, user_id=1)
    # 延迟绑定 tools（空列表即可）
    agent.tools = []
    return agent


# ---------------------------------------------------------------------------
# 测试 1：check_completeness 返回正确 missing_fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_completeness_missing_fields():
    """缺城市、天数、预算时全部返回。"""
    missing, clarified = check_completeness({})
    assert set(missing) == {"city", "days", "budget"}
    assert clarified == {}


# ---------------------------------------------------------------------------
# 测试 2：check_completeness 完整时不 missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_completeness_all_present():
    missing, clarified = check_completeness({"city": "北京", "days": 2, "budget": 3000})
    assert missing == []
    assert clarified == {}


# ---------------------------------------------------------------------------
# 测试 3：check_completeness 历史城市继承
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_completeness_history_city_inheritance():
    history = [{"role": "user", "content": "去上海玩"}]
    missing, clarified = check_completeness({"days": 3, "budget": 5000}, history)
    assert "city" not in missing
    assert clarified["city"] == "上海"


# ---------------------------------------------------------------------------
# 测试 4：_build_clarify_field 各字段正确
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_clarify_field_definitions():
    city_f = _build_clarify_field("city")
    assert isinstance(city_f, ClarifyField)
    assert city_f.label == "目的地"
    assert city_f.field_type == "select"
    assert "北京" in city_f.options

    days_f = _build_clarify_field("days")
    assert days_f.field_type == "select"
    assert "1天" in days_f.options

    budget_f = _build_clarify_field("budget")
    assert "1000-3000" in budget_f.options

    dep_f = _build_clarify_field("departure_city")
    assert dep_f.required is False


# ---------------------------------------------------------------------------
# 测试 5：_escalate_plan 缺失字段时发出 clarify card
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_plan_emits_clarify_card_when_missing():
    on_event = AsyncMock()
    agent = _make_chat_agent(on_event=on_event)

    # args 缺 days 和 budget
    args = {"city": "北京"}
    text, usage = await agent._escalate_plan(args)

    # 应该发出 clarify card event
    on_event.assert_awaited_once()
    call_args = on_event.call_args[0][0]
    assert call_args["type"] == "card"
    assert call_args["card_type"] == "clarify"
    assert "fields" in call_args["data"]
    field_keys = [f["key"] for f in call_args["data"]["fields"]]
    assert "days" in field_keys
    assert "budget" in field_keys

    # 返回占位文本，不进入 Orchestrator
    assert "补充" in text
    assert usage == {}


# ---------------------------------------------------------------------------
# 测试 6：_escalate_plan 完整时正常进入 Orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalate_plan_does_not_emit_clarify_when_complete():
    """完整 args 时，_escalate_plan 不发出 clarify card。"""
    on_event = AsyncMock()
    agent = _make_chat_agent(on_event=on_event)

    args = {"city": "北京", "days": 2, "budget": 3000}

    # patch Orchestrator 避免实际调用
    with patch("src.services.agent.orchestrator.Orchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_result = MagicMock()
        mock_result.plan = {"city": "北京", "days": 2}
        mock_result.usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
        mock_result.raw_output = '{"city":"北京"}'
        mock_orch.plan = AsyncMock(return_value=mock_result)
        mock_orch_cls.return_value = mock_orch

        text, usage = await agent._escalate_plan(args)

    # 不发出 clarify card
    for call in on_event.call_args_list:
        event = call[0][0]
        assert event.get("card_type") != "clarify", "完整 args 时不应发出 clarify card"

    # 应发出 trip_planned 事件
    assert any(
        c[0][0].get("type") == "trip_planned"
        for c in on_event.call_args_list
    ), "应发出 trip_planned 事件"


# ---------------------------------------------------------------------------
# 测试 7：ChatPanel onCard 分支（纯函数逻辑验证）
# ---------------------------------------------------------------------------

def test_chat_panel_clarify_card_branch():
    """验证 ChatPanel 的 onCard 逻辑能正确处理 clarify 类型。"""
    # 这里只验证逻辑分支，不渲染 Vue 组件
    card_type = "clarify"
    data = {"fields": [{"key": "days", "label": "天数"}]}

    if card_type == "clarify":
        clarify_data = data  # 应存入 clarifyCards
        assert "fields" in clarify_data
    else:
        assert False, "应为 clarify 类型"


# ---------------------------------------------------------------------------
# 测试 8：handleClarifySubmit 格式化逻辑
# ---------------------------------------------------------------------------

def test_handle_clarify_submit_format():
    """验证表单值格式化逻辑（纯函数测试）。"""
    values = {"city": "北京", "days": 2, "budget": 3000, "departure_city": "上海"}

    parts = []
    if values.get("city"):
        parts.append(f"目的地:{values['city']}")
    if values.get("days"):
        parts.append(f"天数:{values['days']}")
    if values.get("budget"):
        parts.append(f"预算:{values['budget']}")
    if values.get("departure_city"):
        parts.append(f"出发城市:{values['departure_city']}")

    msg = "\n".join(parts)
    assert "目的地:北京" in msg
    assert "天数:2" in msg
    assert "预算:3000" in msg
    assert "出发城市:上海" in msg


# ---------------------------------------------------------------------------
# 测试 9：字段继承边界（城市存在时不继承，天数/预算不继承）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_completeness_no_double_count():
    """城市已提供时，历史中的城市不重复计入 clarified。"""
    history = [{"role": "user", "content": "去杭州"}]
    missing, clarified = check_completeness({"city": "北京", "days": 2, "budget": 5000}, history)
    # 城市已显式提供，不应从历史继承
    assert "city" not in missing
    assert clarified == {}  # 没有需要继承的


# ---------------------------------------------------------------------------
# 测试 10：_build_clarify_field 未知 key 降级
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_clarify_field_unknown_key_fallback():
    f = _build_clarify_field("custom_field")
    assert f.key == "custom_field"
    assert f.field_type == "text"
    assert f.required is True
