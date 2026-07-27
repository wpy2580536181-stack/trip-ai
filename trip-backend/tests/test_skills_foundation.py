"""Skills 基座测试（Route B：SKILL.md 驱动 + 指令驱动执行）。

验证点：
1. SkillLoader 能解析 SKILL.md 的 frontmatter + 分段。
2. L1 目录只暴露元信息，不泄漏 instructions（渐进式披露）。
3. L2 load_spec 才返回指令（lazy-load：注册后 _spec 为 None）。
4. 三层披露轨迹严格 L1 → L2 → L3。
5. 执行是指令驱动 + 多轮 tool calling：把 SKILL.md 指令交给 LLM，并 bind_tools。
6. select 关键字粗选；未注册技能安全拒绝。
7. AgentEngine.invoke_skill 正确委托到 registry。
8. parse_skill_catalog 仅解析 frontmatter（lazy-load 验证）。
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
    parse_skill_catalog,
)
import src.services.agent.skills as skills_pkg


def _skills_dir():
    """返回 .claude/skills 目录路径（Anthropic 标准）。"""
    here = os.path.dirname(skills_pkg.__file__)
    project_root = os.path.normpath(os.path.join(here, "..", "..", "..", ".."))
    return os.path.join(project_root, ".claude", "skills")


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
        resp.tool_calls = None
        return resp


class FakeMultiTurnLLM:
    """多轮假 LLM：第一次返回 tool_call，第二次返回最终文本。"""

    def __init__(self):
        self.calls = []
        self.bound_tools = None
        self._call_count = 0

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        self._call_count += 1
        resp = MagicMock()
        if self._call_count == 1:
            # 第一次：发起 tool call
            resp.content = ""
            resp.tool_calls = [{"name": "fake_tool", "args": {"q": "test"}, "id": "call_1"}]
        else:
            # 第二次：最终回答
            resp.content = "MULTI_TURN_RESULT"
            resp.tool_calls = None
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


class FakeTool:
    """假工具：模拟 LangChain tool 对象。"""

    def __init__(self, name="fake_tool"):
        self.name = name
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return f"tool_result_for_{args}"


class TestSkillLoader(unittest.TestCase):
    def test_parse_skill_file(self):
        paths = discover_skill_paths(_skills_dir())
        self.assertTrue(paths, "应发现至少一个 SKILL.md")
        tp_path = [p for p in paths if p.endswith("trip-planner/SKILL.md")][0]
        from src.services.agent.skills import parse_skill_file

        cat, spec = parse_skill_file(tp_path)
        self.assertEqual(cat.name, "trip-planner")
        self.assertEqual(cat.kind, "agent")
        # 指令驱动编排的标志：instructions 点名底层工具
        self.assertIn("retrieve_knowledge", spec.instructions)
        self.assertIn("search_hotels", spec.instructions)
        self.assertIn("calculate_distance", spec.instructions)

    def test_parse_skill_catalog_only_frontmatter(self):
        """parse_skill_catalog 仅解析 frontmatter，不解析 body。"""
        paths = discover_skill_paths(_skills_dir())
        tp_path = [p for p in paths if p.endswith("trip-planner/SKILL.md")][0]
        cat = parse_skill_catalog(tp_path)
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "trip-planner")
        self.assertIsInstance(cat, SkillCatalog)
        # catalog 不含 instructions（L1 不泄漏 L2 内容）
        self.assertFalse(hasattr(cat, "instructions"))


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
        spec = self.reg.load_spec("trip-planner")
        self.assertIsInstance(spec, SkillSpec)
        self.assertIn("retrieve_knowledge", spec.instructions)

    def test_lazy_load_spec(self):
        """注册后 _spec 为 None，调用 load_spec() 后才加载。"""
        skill = self.reg.get("trip-planner")
        self.assertIsNotNone(skill)
        # 注册时未解析 body（lazy-load）
        self.assertIsNone(skill._spec)
        # 调用 load_spec 后才有值
        spec = skill.load_spec()
        self.assertIsNotNone(skill._spec)
        self.assertIn("retrieve_knowledge", spec.instructions)

    def test_select_keyword(self):
        self.assertEqual(self.reg.select("帮我规划成都3日游"), "trip-planner")
        self.assertEqual(self.reg.select("从家到公司怎么走最快"), "route-optimize")
        self.assertIsNone(self.reg.select("今天天气怎么样"))

    async def test_route_skill_llm_selects(self):
        """LLM 读 L1 目录自行选 skill（deprecated 但仍可用）。"""
        llm = FakeRouterLLM("trip-planner")
        name = await self.reg.route_skill("帮我规划成都3日游", llm)
        self.assertEqual(name, "trip-planner")
        # L1 目录被送进路由器上下文
        self.assertIn("trip-planner", llm.calls[0][0]["content"])

    async def test_route_skill_none(self):
        llm = FakeRouterLLM("NONE")
        self.assertIsNone(await self.reg.route_skill("今天天气不错", llm))

    async def test_route_skill_falls_back_to_keyword(self):
        """LLM 返回无法解析的文本 → 关键字兜底。"""
        llm = FakeRouterLLM("我不知道")
        self.assertEqual(
            await self.reg.route_skill("从家到公司怎么走最快", llm), "route-optimize"
        )

    def test_l2_loads_full_body(self):
        """L2 激活层加载整篇 SKILL.md 正文，而非仅结构化片段。"""
        spec = self.reg.load_spec("trip-planner")
        self.assertIn("Instructions", spec.body)
        self.assertIn("retrieve_knowledge", spec.body)
        self.assertTrue(spec.resources)  # 检测到 references/ 引用


class TestExecuteInstructionDriven(unittest.IsolatedAsyncioTestCase):
    async def test_disclosure_order_and_tool_binding(self):
        reg = SkillRegistry()
        load_builtin_skills(reg)
        llm = FakeLLM()
        tools = [FakeTool("t1"), FakeTool("t2")]
        ctx = SkillContext(llm=llm, tools=tools, registry=reg, user_input="帮我规划成都3日游")
        result = await reg.execute("trip-planner", ctx, city="成都", days=3)

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

    async def test_multi_turn_tool_calling(self):
        """多轮 tool calling：LLM 先调工具，再给出最终回答。"""
        reg = SkillRegistry()
        load_builtin_skills(reg)
        llm = FakeMultiTurnLLM()
        tool = FakeTool("fake_tool")
        ctx = SkillContext(llm=llm, tools=[tool], registry=reg, user_input="帮我规划成都3日游")
        result = await reg.execute("trip-planner", ctx, city="成都")

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "MULTI_TURN_RESULT")
        # LLM 被调用了 2 次（第一次 tool call，第二次最终回答）
        self.assertEqual(len(llm.calls), 2)
        # 工具被调用了 1 次
        self.assertEqual(len(tool.calls), 1)
        self.assertEqual(tool.calls[0], {"q": "test"})

    async def test_l3_resources_loaded_on_execute(self):
        """L3 执行层：SKILL.md 引用的 references/ 按需读入上下文。"""
        reg = SkillRegistry()
        load_builtin_skills(reg)
        llm = FakeLLM()
        ctx = SkillContext(llm=llm, tools=[FakeTool("t1")], registry=reg, user_input="帮我规划成都3日游")
        result = await reg.execute("trip-planner", ctx, city="成都")
        # trip-planner SKILL.md 引用了 references/itinerary-notes.md → L3 资源按需加载
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
        result = await engine.invoke_skill("trip-planner", user_input="q", ctx=ctx, city="成都")
        self.assertEqual(called["name"], "trip-planner")
        self.assertEqual(called["kwargs"]["city"], "成都")
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
