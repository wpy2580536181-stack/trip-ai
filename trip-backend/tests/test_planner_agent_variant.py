"""PlannerAgent variant prompt 注入单测。

覆盖：
- variant_type=None 时不追加约束
- variant_type='economy' 时追加经济型约束
- variant_type='comfort' 时追加舒适型约束
- variant_type='photo' 时追加打卡型约束
- variant_type='unknown' 时不追加约束
- 不破坏现有 _build_system_prompt 行为
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from src.services.agent.agents.planner_agent import PlannerAgent
from src.services.agent.schemas import PlannerInput, ResearchBundle


@pytest.fixture
def agent():
    return PlannerAgent(llm=MagicMock())


@pytest.fixture
def bundle():
    return ResearchBundle(
        attractions="景点：故宫、天安门",
        food="美食：烤鸭",
        hotels="酒店：王府井酒店",
    )


def _make_input(bundle: ResearchBundle, variant_type: str | None = None) -> PlannerInput:
    return PlannerInput(
        bundle=bundle,
        city="北京",
        days=3,
        budget=5000,
        variant_type=variant_type,
    )


class TestVariantPromptInjection:
    """variant prompt 注入验证。"""

    async def test_no_variant_type_no_constraint(self, agent: PlannerAgent, bundle: ResearchBundle):
        """variant_type=None 时不追加任何 variant 约束"""
        inp = _make_input(bundle)
        prompt = agent._build_system_prompt(inp)
        assert "经济型约束" not in prompt
        assert "舒适型约束" not in prompt
        assert "打卡型约束" not in prompt

    async def test_economy_variant_appends_constraint(self, agent: PlannerAgent, bundle: ResearchBundle):
        """economy variant 追加经济型约束 prompt"""
        inp = _make_input(bundle, variant_type="economy")
        prompt = agent._build_system_prompt(inp)
        assert "经济型约束" in prompt
        assert "免费景点" in prompt
        assert "公共交通" in prompt
        assert "经济型酒店" in prompt

    async def test_comfort_variant_appends_constraint(self, agent: PlannerAgent, bundle: ResearchBundle):
        """comfort variant 追加舒适型约束 prompt"""
        inp = _make_input(bundle, variant_type="comfort")
        prompt = agent._build_system_prompt(inp)
        assert "舒适型约束" in prompt
        assert "6000 步" in prompt
        assert "6-8 个核心景点" in prompt

    async def test_photo_variant_appends_constraint(self, agent: PlannerAgent, bundle: ResearchBundle):
        """photo variant 追加打卡型约束 prompt"""
        inp = _make_input(bundle, variant_type="photo")
        prompt = agent._build_system_prompt(inp)
        assert "打卡型约束" in prompt
        assert "网红" in prompt
        assert "出片" in prompt
        assert "4-6 个" in prompt

    async def test_unknown_variant_type_no_constraint(self, agent: PlannerAgent, bundle: ResearchBundle):
        """未知 variant_type 不追加约束"""
        inp = _make_input(bundle, variant_type="unknown")
        prompt = agent._build_system_prompt(inp)
        assert "经济型约束" not in prompt
        assert "舒适型约束" not in prompt
        assert "打卡型约束" not in prompt

    async def test_variant_constraint_appended_after_feedback(self, agent: PlannerAgent, bundle: ResearchBundle):
        """variant 约束在 feedback 之后追加（prompt 顺序正确）"""
        inp = PlannerInput(
            bundle=bundle,
            city="北京",
            days=3,
            budget=5000,
            variant_type="economy",
            feedback="请减少步行距离",
        )
        prompt = agent._build_system_prompt(inp)
        feedback_pos = prompt.find("修改要求")
        variant_pos = prompt.find("经济型约束")
        assert feedback_pos != -1, "feedback 段落未找到"
        assert variant_pos != -1, "variant 约束未找到"
        assert variant_pos > feedback_pos, "variant 约束应在 feedback 之后"

    async def test_partial_mode_with_variant(self, agent: PlannerAgent, bundle: ResearchBundle):
        """局部模式（target_days）下 variant_type 也能正常注入"""
        inp = PlannerInput(
            bundle=bundle,
            city="北京",
            days=3,
            budget=5000,
            target_days=[2],
            variant_type="comfort",
        )
        prompt = agent._build_system_prompt(inp)
        assert "舒适型约束" in prompt
        assert "第2天" in prompt  # partial prompt 内容
