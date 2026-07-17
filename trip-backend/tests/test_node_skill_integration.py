"""节点级 Skills 集成测试。

验证 planner / chat_planner / legacy_agent 三个节点已真正接入
「L1 粗选 → L2 规格注入 → L3 指令驱动执行」的技能调用路径，
且无人选 / 技能失败时优雅降级到原有逻辑。

不依赖真实 LLM / DB / 网络：用 FakeRegistry + FakeLLM，并 patch
build_skill_context 避免触发真实工具导入。
"""

import unittest
from unittest.mock import patch, MagicMock

from langchain_core.messages import AIMessage

from src.services.agent.skills.types import SkillContext, SkillResult
from src.services.agent.nodes.planner import planner_node
from src.services.agent.nodes.chat_planner import chat_planner_node
from src.services.agent.nodes.legacy_agent import legacy_agent_node


class FakeLLM:
    def __init__(self, text: str = "fallback-plan"):
        self.text = text

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages, **kwargs):
        return AIMessage(content=self.text)

    async def astream_events(self, input, version=None):
        yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content=self.text)}}
        yield {"event": "on_chat_model_end", "data": {"output": AIMessage(content=self.text)}}


class FakeRegistry:
    """route_skill 返回预置技能名；execute 返回预置 SkillResult（不触真 LLM）。"""

    def __init__(self, selected=None, result=None):
        self.selected = selected
        self.result = result or SkillResult(
            skill=selected or "?", ok=True, content="", disclosure=["L1:catalog:x"]
        )
        self.execute_calls = []

    async def route_skill(self, query, llm):
        # 模拟 LLM 驱动选 skill（文章标准：匹配是推理行为）
        return self.selected

    def select(self, query):
        return self.selected

    def catalog_prompt(self, header: str = "# 可用技能") -> str:
        # 该桩不暴露目录内容（降级测试不校验目录文本）
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
        reg = FakeRegistry(
            selected="行程规划",
            result=SkillResult(
                skill="行程规划",
                ok=True,
                content='{"city":"成都","days":3,"daily_plan":[]}',
                disclosure=["L1:catalog:行程规划", "L2:spec:行程规划", "L3:execute:行程规划"],
            ),
        )
        state = {
            "message": "帮我规划成都3日游",
            "city": "成都",
            "days": 3,
            "budget": None,
            "departure_city": None,
        }
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ):
            out = await planner_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertEqual(out["raw_output"], '{"city":"成都","days":3,"daily_plan":[]}')
        self.assertEqual(out["skill_used"], "行程规划")
        self.assertEqual(len(reg.execute_calls), 1)
        # 透传了结构化入参给技能
        self.assertEqual(reg.execute_calls[0]["kwargs"].get("city"), "成都")
        self.assertEqual(reg.execute_calls[0]["kwargs"].get("days"), 3)

    async def test_no_skill_falls_back_to_planner(self):
        reg = FakeRegistry(selected=None)
        state = {
            "message": "帮我规划成都3日游",
            "city": "成都",
            "days": 3,
            "budget": None,
            "departure_city": None,
        }
        # 降级路径走 build_planner_prompt → _invoke_llm(llm)，用 AsyncMock 替代真实 LLM 链
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ), patch(
            "src.services.agent.nodes.planner._invoke_llm",
            new=unittest.mock.AsyncMock(return_value=("降级输出", {"prompt": 0, "completion": 0, "total": 0, "cached": 0})),
        ):
            out = await planner_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertEqual(out["raw_output"], "降级输出")
        self.assertNotIn("skill_used", out)
        self.assertEqual(len(reg.execute_calls), 0)


class TestChatPlannerNodeSkill(unittest.IsolatedAsyncioTestCase):
    async def test_skill_hit_emits_chunk_and_returns(self):
        events = []
        reg = FakeRegistry(
            selected="行程规划",
            result=SkillResult(
                skill="行程规划", ok=True, content="行程内容",
                disclosure=["L1:catalog:行程规划", "L2:spec:行程规划", "L3:execute:行程规划"],
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
        cfg = _config(registry=reg, llm=FakeLLM())
        cfg["configurable"]["on_event"] = lambda e: _collect(events, e)
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ):
            out = await chat_planner_node(state, cfg)
        self.assertEqual(out["raw_output"], "行程内容")
        self.assertEqual(out["skill_used"], "行程规划")
        # 通过 on_event 发射了 chunk
        self.assertTrue(any(e.get("type") == "chunk" for e in events))


class TestLegacyAgentNodeSkill(unittest.IsolatedAsyncioTestCase):
    async def test_skill_hit_uses_skill_output(self):
        reg = FakeRegistry(
            selected="路线优化",
            result=SkillResult(
                skill="路线优化", ok=True, content="最优路线结果",
                disclosure=["L1:catalog:路线优化", "L2:spec:路线优化", "L3:execute:路线优化"],
            ),
        )
        state = {"message": "从家到公司怎么走最快", "city": "", "days": None,
                 "budget": None, "departure_city": None}
        with patch(
            "src.services.agent.skills.runtime.build_skill_context",
            return_value=_fake_ctx(),
        ):
            out = await legacy_agent_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertEqual(out["raw_output"], "最优路线结果")
        self.assertEqual(out["skill_used"], "路线优化")

    async def test_no_skill_falls_back_to_agent(self):
        reg = FakeRegistry(selected=None)
        state = {"message": "你好", "city": "", "days": None,
                 "budget": None, "departure_city": None}
        # build_agent 为 None → 降级返回固定提示
        out = await legacy_agent_node(state, _config(registry=reg, llm=FakeLLM()))
        self.assertIn("无法处理", out["raw_output"])
        self.assertNotIn("skill_used", out)


if __name__ == "__main__":
    unittest.main()
