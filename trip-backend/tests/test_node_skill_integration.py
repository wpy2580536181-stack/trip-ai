"""节点级 Skills 集成测试。

验证 planner / chat_planner / legacy_agent 三个节点已真正接入
「主 LLM 绑定 select_skill 工具 → 检测 tool call → 执行技能」的新架构路径，
且无人选 / 技能失败时优雅降级到原有逻辑。

不依赖真实 LLM / DB / 网络：用 FakeRegistry + FakeLLM，并 patch
build_skill_context 避免触发真实工具导入。
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from langchain_core.messages import AIMessage

from src.services.agent.skills.types import SkillContext, SkillResult
from src.services.agent.nodes.planner import planner_node
from src.services.agent.nodes.chat_planner import chat_planner_node
from src.services.agent.nodes.legacy_agent import legacy_agent_node


class FakeLLM:
    """假 LLM：返回预置文本，支持 bind_tools。"""

    def __init__(self, text: str = "fallback-plan"):
        self.text = text
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages, **kwargs):
        resp = AIMessage(content=self.text)
        resp.tool_calls = None
        return resp

    async def astream_events(self, input, version=None):
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content=self.text)}}
        yield {"event": "on_chat_model_end", "data": {"output": AIMessage(content=self.text)}}


class FakeLLMWithSkillCall:
    """假 LLM：返回 select_skill tool call（模拟主 LLM 选中技能）。"""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages, **kwargs):
        resp = AIMessage(content="")
        resp.tool_calls = [{"name": "select_skill", "args": {"skill_name": self.skill_name}, "id": "call_1"}]
        return resp


class FakeRegistry:
    """route_skill 返回预置技能名；execute 返回预置 SkillResult（不触真 LLM）。"""

    def __init__(self, selected=None, result=None):
        self.selected = selected
        self.result = result or SkillResult(
            skill=selected or "?", ok=True, content="", disclosure=["L1:catalog:x"]
        )
        self.execute_calls = []

    def get(self, name):
        """模拟技能查找。"""
        if name == self.selected:
            return MagicMock()
        return None

    async def route_skill(self, query, llm):
        return self.selected

    def select(self, query):
        return self.selected

    def catalog_prompt(self, header: str = "# 可用技能") -> str:
        if self.selected:
            return f"- **{self.selected}** [agent]：测试技能（tags: test）"
        return ""

    async def execute(self, name, ctx, **kwargs):
        self.execute_calls.append({"name": name, "kwargs": kwargs})
        return self.result


def _config(registry, llm):
    return {
        "configurable": {
            "llm": llm,
            "fallback_llm_config": None,
            "on_event": None,
            "skill_registry": registry,
        }
    }


def _fake_ctx():
    return SkillContext(llm=None, tools=[], registry=None, user_input="")


async def _collect(events, e):
    events.append(e)


class TestPlannerNodeSkill(unittest.IsolatedAsyncioTestCase):
    async def test_skill_hit_uses_skill_output(self):
        """主 LLM 调用 select_skill → 技能执行 → 返回技能输出。"""
        reg = FakeRegistry(
            selected="trip-planner",
            result=SkillResult(
                skill="trip-planner",
                ok=True,
                content='{"city":"成都","days":3,"daily_plan":[]}',
                disclosure=["L1:catalog:trip-planner", "L2:spec:trip-planner", "L3:execute:trip-planner"],
            ),
        )
        state = {
            "message": "帮我规划成都3日游",
            "city": "成都",
            "days": 3,
            "budget": None,
            "departure_city": None,
        }
        # 模拟 _invoke_llm_with_skill 返回含 select_skill tool call 的响应
        fake_resp = AIMessage(content="")
        fake_resp.tool_calls = [{"name": "select_skill", "args": {"skill_name": "trip-planner"}, "id": "call_1"}]
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ), patch(
            "src.services.agent.nodes.planner._invoke_llm_with_skill",
            new=AsyncMock(return_value=("", {"prompt": 0, "completion": 0, "total": 0, "cached": 0}, fake_resp)),
        ):
            out = await planner_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertEqual(out["raw_output"], '{"city":"成都","days":3,"daily_plan":[]}')
        self.assertEqual(out["skill_used"], "trip-planner")
        self.assertEqual(len(reg.execute_calls), 1)
        # 透传了结构化入参给技能
        self.assertEqual(reg.execute_calls[0]["kwargs"].get("city"), "成都")
        self.assertEqual(reg.execute_calls[0]["kwargs"].get("days"), 3)

    async def test_no_skill_falls_back_to_planner(self):
        """LLM 不调 select_skill → 使用 LLM 文本输出作为规划结果。"""
        reg = FakeRegistry(selected=None)
        state = {
            "message": "帮我规划成都3日游",
            "city": "成都",
            "days": 3,
            "budget": None,
            "departure_city": None,
        }
        # LLM 不调 select_skill，直接返回文本
        fake_resp = AIMessage(content="降级输出")
        fake_resp.tool_calls = None
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ), patch(
            "src.services.agent.nodes.planner._invoke_llm_with_skill",
            new=AsyncMock(return_value=("降级输出", {"prompt": 0, "completion": 0, "total": 0, "cached": 0}, fake_resp)),
        ):
            out = await planner_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertEqual(out["raw_output"], "降级输出")
        self.assertNotIn("skill_used", out)
        self.assertEqual(len(reg.execute_calls), 0)


class TestChatPlannerNodeSkill(unittest.IsolatedAsyncioTestCase):
    async def test_skill_hit_emits_chunk_and_returns(self):
        events = []
        reg = FakeRegistry(
            selected="trip-planner",
            result=SkillResult(
                skill="trip-planner", ok=True, content="行程内容",
                disclosure=["L1:catalog:trip-planner", "L2:spec:trip-planner", "L3:execute:trip-planner"],
            ),
        )
        state = {
            "message": "规划杭州2日游",
            "city": "杭州",
            "days": 2,
            "budget": None,
            "departure_city": None,
            "conversation_history": [],
        }
        cfg = _config(registry=reg, llm=FakeLLMWithSkillCall("trip-planner"))
        cfg["configurable"]["on_event"] = lambda e: _collect(events, e)
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ):
            out = await chat_planner_node(state, cfg)
        self.assertEqual(out["raw_output"], "行程内容")
        self.assertEqual(out["skill_used"], "trip-planner")
        # 通过 on_event 发射了 chunk
        self.assertTrue(any(e.get("type") == "chunk" for e in events))


class TestLegacyAgentNodeSkill(unittest.IsolatedAsyncioTestCase):
    async def test_skill_hit_uses_skill_output(self):
        reg = FakeRegistry(
            selected="route-optimize",
            result=SkillResult(
                skill="route-optimize", ok=True, content="最优路线结果",
                disclosure=["L1:catalog:route-optimize", "L2:spec:route-optimize", "L3:execute:route-optimize"],
            ),
        )
        state = {"message": "从家到公司怎么走最快", "city": "", "days": None,
                 "budget": None, "departure_city": None}
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ):
            out = await legacy_agent_node(state, _config(registry=reg, llm=FakeLLMWithSkillCall("route-optimize")))
        self.assertEqual(out["raw_output"], "最优路线结果")
        self.assertEqual(out["skill_used"], "route-optimize")

    async def test_no_skill_falls_back_to_agent(self):
        reg = FakeRegistry(selected=None)
        state = {"message": "你好", "city": "", "days": None,
                 "budget": None, "departure_city": None}
        # LLM 不调 select_skill + build_agent 为 None → 降级返回固定提示
        out = await legacy_agent_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertIn("无法处理", out["raw_output"])
        self.assertNotIn("skill_used", out)


if __name__ == "__main__":
    unittest.main()
