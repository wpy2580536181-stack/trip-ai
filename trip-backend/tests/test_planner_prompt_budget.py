"""planner prompt 预算段落测试。PB1-PB4 用例。

覆盖：
- PB1 无 budget_correction → 渲染 allocator 的 5 项分解 + 每日活动费用上限
- PB2 有 budget_correction → 渲染修正段落（轮次/超支/目标金额），且 planner_agent 接线生效
- PB3 travel_style=budget → 占比与 comfort 不同（门票 15%）
- PB4 budget≤2000 低档兜底 → tickets 提升到 15%（1500×15%=225 → 取整 220）
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.services.agent.agents.planner_agent import PlannerAgent
from src.services.agent.planner_prompt import build_planner_prompt
from src.services.agent.schemas import CorrectorAction, PlannerInput, ResearchBundle


def _correction() -> CorrectorAction:
    """第 1 轮修正：门票 ×0.6、餐饮 ×0.9（基于 10000/5 天 comfort 分解）。"""
    return CorrectorAction(
        round=1,
        over_amount=400,
        target_allocation={
            "accommodation": 4000,
            "food": 2250,
            "transportation": 2000,
            "tickets": 600,
            "other": 500,
        },
        instructions=(
            "当前第 1 轮预算修正：超支 400 元。\n"
            "目标分解：住宿目标 ≤ 4000 元、餐饮目标 ≤ 2250 元、交通目标 ≤ 2000 元、"
            "门票目标 ≤ 600 元、其他目标 ≤ 500 元。\n"
            "请按目标重新组合行程，替换指引：优先替换为免费景点，收紧餐饮消费。"
        ),
    )


class TestPlannerPromptBudget:
    def test_pb1_comfort_default_allocation(self):
        """PB1: 无修正时渲染 allocator 的 5 项分解 + 每日活动费用上限"""
        prompt = build_planner_prompt(city="北京", budget=10000, days=5)

        assert "【预算分解目标】" in prompt
        assert "住宿 ≤ 4000 元" in prompt
        assert "餐饮 ≤ 2500 元" in prompt
        assert "交通 ≤ 2000 元" in prompt
        assert "门票 ≤ 1000 元" in prompt
        assert "其他 ≤ 500 元" in prompt
        assert "每日活动费用上限 ≤ 600 元" in prompt

    def test_pb2_correction_paragraph(self):
        """PB2: 有 budget_correction 时渲染修正段落，且 planner_agent 接线生效"""
        prompt = build_planner_prompt(
            city="北京", budget=10000, days=5, budget_correction=_correction()
        )
        assert "【预算修正指令】" in prompt
        assert "修正" in prompt
        assert "第 1 轮" in prompt
        assert "400 元" in prompt
        assert "门票 ≤ 600 元" in prompt

        agent = PlannerAgent(llm=MagicMock())
        inp = PlannerInput(
            bundle=ResearchBundle(attractions="故宫"),
            city="北京",
            days=5,
            budget=10000,
            budget_correction=_correction(),
        )
        agent_prompt = agent._build_system_prompt(inp)
        assert "【预算修正指令】" in agent_prompt
        assert "第 1 轮" in agent_prompt
        assert "门票 ≤ 600 元" in agent_prompt

    def test_pb3_budget_style(self):
        """PB3: travel_style=budget 时占比不同（住宿 35%、门票 15%、餐饮 30%）"""
        prompt = build_planner_prompt(
            city="北京",
            budget=10000,
            days=5,
            user_preferences={"travel_style": "budget"},
        )
        assert "住宿 ≤ 3500 元" in prompt
        assert "餐饮 ≤ 3000 元" in prompt
        assert "门票 ≤ 1500 元" in prompt

    def test_pb4_low_budget_fallback(self):
        """PB4: budget≤2000 低档兜底 tickets=15%（1500×15%=225 → 取整 220/230）"""
        prompt = build_planner_prompt(city="北京", budget=1500, days=3)
        assert "门票 ≤ 220 元" in prompt or "门票 ≤ 230 元" in prompt
        assert "住宿 ≤ 450 元" in prompt
