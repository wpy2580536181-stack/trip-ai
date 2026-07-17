"""行程规划 Skill 测试（Route B：SKILL.md 驱动）。

验证：
1. 内置技能从 SKILL.md 加载，select 能命中「行程规划」。
2. 技能的执行是「指令驱动」：SKILL.md 的 instructions 点名底层工具，交给 LLM 做
   tool calling 自行编排——而非写死的代码流程。
3. 三层披露轨迹严格 L1 → L2 → L3。
4. 未注册技能安全拒绝。
"""

import asyncio
import unittest
from unittest.mock import MagicMock

from src.services.agent.skills import (
    SkillRegistry,
    SkillContext,
    SkillResult,
    load_builtin_skills,
)


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        resp = MagicMock()
        resp.content = "FAKE_ITINERARY_JSON"
        return resp


class TestItineraryPlanningSkill(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reg = SkillRegistry()
        load_builtin_skills(self.reg)

    def test_builtin_skill_loaded_from_markdown(self):
        self.assertIsNotNone(self.reg.get("行程规划"))
        self.assertEqual(self.reg.get("行程规划").catalog.kind, "agent")

    def test_select_hits_itinerary(self):
        self.assertEqual(self.reg.select("帮我规划成都3日游"), "行程规划")

    def test_spec_drives_orchestration(self):
        """SKILL.md 的 instructions 点名底层工具 → 指令驱动编排。"""
        spec = self.reg.load_spec("行程规划")
        for tool in ("retrieve_knowledge", "search_hotels", "calculate_distance"):
            self.assertIn(tool, spec.instructions)

    async def test_execute_instruction_driven(self):
        llm = FakeLLM()
        tools = ["retrieve_knowledge", "search_hotels", "calculate_distance"]
        ctx = SkillContext(llm=llm, tools=tools, registry=self.reg, user_input="帮我规划成都3日游")
        result = await self.reg.execute("行程规划", ctx, city="成都", days=3)

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "FAKE_ITINERARY_JSON")
        # 三层披露
        layers = [d.split(":", 1)[0] for d in result.disclosure]
        self.assertEqual(layers, ["L1", "L2", "L3"])
        # LLM 被调用且 tools 已绑定（tool calling 路径）
        self.assertEqual(len(llm.calls), 1)
        self.assertIs(llm.bound_tools, tools)
        # SKILL.md 指令到达 LLM
        system_msg = llm.calls[0][0]["content"]
        self.assertIn("retrieve_knowledge", system_msg)
        self.assertIn("成都", llm.calls[0][1]["content"])
        # L3：引用的 references/itinerary-notes.md 按需加载进上下文（体现在 L3 标签内）
        self.assertTrue(
            any(d.startswith("L3:execute") and "resources=" in d for d in result.disclosure)
        )
        self.assertIn("预算分配", system_msg)

    async def test_unregistered_safe_reject(self):
        ctx = SkillContext(llm=FakeLLM())
        result = await self.reg.execute("ghost", ctx)
        self.assertFalse(result.ok)
        self.assertIn("未注册", result.error)


if __name__ == "__main__":
    unittest.main()
