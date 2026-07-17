"""Skills 基座测试（Route B：SKILL.md 驱动 + 指令驱动执行）。

验证点：
1. SkillLoader 能解析 SKILL.md 的 frontmatter + 分段。
2. L1 目录只暴露元信息，不泄漏 instructions（渐进式披露）。
3. L2 load_spec 才返回指令。
4. 三层披露轨迹严格 L1 → L2 → L3。
5. 执行是指令驱动：把 SKILL.md 指令交给 LLM，并 bind_tools（tool calling）。
6. select 关键字粗选；未注册技能安全拒绝。
7. AgentEngine.invoke_skill 正确委托到 registry。
"""

import asyncio
import os
import unittest
from unittest.mock import MagicMock

from src.services.agent.skills import (
    SkillRegistry,
    SkillCatalog,
    SkillSpec,
    SkillContext,
    SkillResult,
    get_skill_registry,
    load_builtin_skills,
    discover_skill_paths,
)
import src.services.agent.skills as skills_pkg


def _skills_dir():
    return os.path.join(os.path.dirname(skills_pkg.__file__), "skills")


class FakeLLM:
    """离线假 LLM：记录收到的消息与绑定的 tools。"""

    def __init__(self):
        self.calls = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        resp = MagicMock()
        resp.content = "FAKE_RESULT"
        return resp


class FakeRouterLLM:
    """路由器假 LLM：返回预置文本（技能名或 NONE）。"""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        resp = MagicMock()
        resp.content = self.text
        return resp


class TestSkillLoader(unittest.TestCase):
    def test_parse_skill_file(self):
        paths = discover_skill_paths(_skills_dir())
        self.assertTrue(paths, "应发现至少一个 SKILL.md")
        it_path = [p for p in paths if p.endswith("itinerary/SKILL.md")][0]
        from src.services.agent.skills import parse_skill_file

        cat, spec = parse_skill_file(it_path)
        self.assertEqual(cat.name, "行程规划")
        self.assertEqual(cat.kind, "agent")
        self.assertIn("行程", cat.tags)
        # 指令驱动编排的标志：instructions 点名底层工具
        self.assertIn("retrieve_knowledge", spec.instructions)
        self.assertIn("search_hotels", spec.instructions)
        self.assertIn("calculate_distance", spec.instructions)


class TestProgressiveDisclosure(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reg = SkillRegistry()
        load_builtin_skills(self.reg)

    def test_l1_catalog_only_metadata(self):
        """L1 目录不泄漏指令本身。"""
        for c in self.reg.list_catalog():
            self.assertIsInstance(c, SkillCatalog)
            self.assertFalse(hasattr(c, "instructions"))
            # 描述里不应出现工具调用细节
            self.assertNotIn("retrieve_knowledge", c.description)

    def test_l2_load_spec_has_instructions(self):
        spec = self.reg.load_spec("行程规划")
        self.assertIsInstance(spec, SkillSpec)
        self.assertIn("retrieve_knowledge", spec.instructions)

    def test_select_keyword(self):
        self.assertEqual(self.reg.select("帮我规划成都3日游"), "行程规划")
        self.assertEqual(self.reg.select("成都住哪好"), "酒店搜索")
        self.assertEqual(self.reg.select("从家到公司怎么走最快"), "路线优化")
        self.assertIsNone(self.reg.select("今天天气怎么样"))

    async def test_route_skill_llm_selects(self):
        """文章标准：LLM 读 L1 目录自行选 skill（匹配是推理）。"""
        llm = FakeRouterLLM("行程规划")
        name = await self.reg.route_skill("帮我规划成都3日游", llm)
        self.assertEqual(name, "行程规划")
        # L1 目录被送进路由器上下文（常驻/按需加载的入口）
        self.assertIn("行程规划", llm.calls[0][0]["content"])

    async def test_route_skill_none(self):
        llm = FakeRouterLLM("NONE")
        self.assertIsNone(await self.reg.route_skill("今天天气不错", llm))

    async def test_route_skill_falls_back_to_keyword(self):
        """LLM 返回无法解析的文本 → 关键字兜底。"""
        llm = FakeRouterLLM("我不知道")
        self.assertEqual(
            await self.reg.route_skill("从家到公司怎么走最快", llm), "路线优化"
        )

    def test_l2_loads_full_body(self):
        """L2 激活层加载整篇 SKILL.md 正文，而非仅结构化片段。"""
        spec = self.reg.load_spec("行程规划")
        self.assertIn("Instructions", spec.body)
        self.assertIn("retrieve_knowledge", spec.body)
        self.assertTrue(spec.resources)  # 检测到 references/ 引用


class TestExecuteInstructionDriven(unittest.IsolatedAsyncioTestCase):
    async def test_disclosure_order_and_tool_binding(self):
        reg = SkillRegistry()
        load_builtin_skills(reg)
        llm = FakeLLM()
        tools = ["t1", "t2"]
        ctx = SkillContext(llm=llm, tools=tools, registry=reg, user_input="帮我规划成都3日游")
        result = await reg.execute("行程规划", ctx, city="成都", days=3)

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "FAKE_RESULT")
        # 三层披露轨迹顺序
        layers = [d.split(":", 1)[0] for d in result.disclosure]
        self.assertEqual(layers, ["L1", "L2", "L3"])
        # 指令驱动：LLM 被调用，且 tools 被绑定（tool calling 路径）
        self.assertEqual(len(llm.calls), 1)
        self.assertIs(llm.bound_tools, tools)
        # SKILL.md 指令真正到达 LLM 的系统提示词
        system_msg = llm.calls[0][0]["content"]
        self.assertIn("retrieve_knowledge", system_msg)

    async def test_l3_resources_loaded_on_execute(self):
        """L3 执行层：SKILL.md 引用的 references/ 按需读入上下文。"""
        reg = SkillRegistry()
        load_builtin_skills(reg)
        llm = FakeLLM()
        ctx = SkillContext(llm=llm, tools=["t1"], registry=reg, user_input="帮我规划成都3日游")
        result = await reg.execute("行程规划", ctx, city="成都")
        # 行程规划 SKILL.md 引用了 references/itinerary-notes.md → L3 资源按需加载
        self.assertTrue(
            any(d.startswith("L3:execute") and "resources=" in d for d in result.disclosure)
        )
        system_msg = llm.calls[0][0]["content"]
        self.assertIn("预算分配", system_msg)  # L3 资源内容进入上下文

    async def test_unregistered_safe_reject(self):
        reg = SkillRegistry()
        ctx = SkillContext(llm=FakeLLM())
        result = await reg.execute("ghost", ctx)
        self.assertFalse(result.ok)
        self.assertIn("未注册", result.error)


class TestSingleton(unittest.TestCase):
    def test_singleton(self):
        self.assertIs(get_skill_registry(), get_skill_registry())


class TestAgentEngineDelegation(unittest.IsolatedAsyncioTestCase):
    async def test_invoke_skill_delegates(self):
        from src.services.agent.agent_engine import AgentEngine

        engine = AgentEngine.__new__(AgentEngine)
        reg = SkillRegistry()
        load_builtin_skills(reg)
        engine.skill_registry = reg

        called = {}

        async def fake_execute(name, ctx, **kwargs):
            called["name"] = name
            called["kwargs"] = kwargs
            return SkillResult(skill=name, ok=True, content="x")

        engine.skill_registry.execute = fake_execute
        ctx = SkillContext(registry=reg)
        result = await engine.invoke_skill("行程规划", user_input="q", ctx=ctx, city="成都")
        self.assertEqual(called["name"], "行程规划")
        self.assertEqual(called["kwargs"]["city"], "成都")
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
