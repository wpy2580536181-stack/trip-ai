"""review 分项校验测试。R1-R7 用例。

对应任务文档 tasks/budget-control-and-cost-fidelity-plan.md T5。
"""

import pytest
from unittest.mock import patch

from src.services.agent.review import review
from src.services.agent.schemas import BudgetAllocation, ResearchBundle

ALLOC = BudgetAllocation(
    budget=10000,
    days=5,
    style="comfort",
    allocation={
        "accommodation": 4000,
        "food": 2500,
        "transportation": 2000,
        "tickets": 1000,
        "other": 500,
    },
    daily_activity_limit=600,
)


def _make_plan(total_budget: int, breakdown: dict) -> str:
    import json
    plan = {
        "city": "北京",
        "days": 5,
        "totalBudget": total_budget,
        "dailyItinerary": [
            {
                "day": 1,
                "morning": {"spot": "天安门"},
                "afternoon": {"spot": "故宫"},
                "evening": {"spot": ""},
            }
        ]
        * 5,
        "budgetBreakdown": breakdown,
        "tips": [],
        "warnings": [],
    }
    return json.dumps(plan, ensure_ascii=False)


BASE_BREAKDOWN = {
    "accommodation": 4000,
    "food": 2500,
    "transportation": 2000,
    "tickets": 1000,
    "other": 500,
}


class TestReviewBudgetItems:
    @pytest.mark.asyncio
    async def test_r1_single_item_over_limit_rejected(self):
        """R1: 单项超限 >1.15 打回，feedback 含具体项与金额。"""
        breakdown = dict(BASE_BREAKDOWN, tickets=3000)
        parsed, result = await review(
            raw_output=_make_plan(10000, breakdown),
            bundle=None,
            budget=10000,
            days=5,
            alloc=ALLOC,
        )
        assert result.passed is False
        assert result.code_checks.get("budget_items") != "ok"
        assert "门票" in result.feedback
        assert "2000" in result.feedback

    @pytest.mark.asyncio
    async def test_r2_single_item_within_elasticity_passed(self):
        """R2: 单项超限但 ≤1.15 弹性放行。"""
        breakdown = dict(BASE_BREAKDOWN, tickets=1100)
        parsed, result = await review(
            raw_output=_make_plan(10000, breakdown),
            bundle=None,
            budget=10000,
            days=5,
            alloc=ALLOC,
        )
        assert result.passed is True
        assert result.code_checks.get("budget_items") == "ok"

    @pytest.mark.asyncio
    async def test_r3_multiple_violations_collected(self):
        """R3: 多项超限，violations 齐全，over_amount 为求和。"""
        breakdown = dict(BASE_BREAKDOWN, tickets=3000, food=4000)
        parsed, result = await review(
            raw_output=_make_plan(11000, breakdown),
            bundle=None,
            budget=10000,
            days=5,
            alloc=ALLOC,
        )
        assert result.passed is False
        checks = result.code_checks.get("budget_items")
        assert isinstance(checks, list) and len(checks) == 2
        keys = {c["key"] for c in checks}
        assert keys == {"tickets", "food"}
        assert sum(c["over"] for c in checks) == (3000 - 1000) + (4000 - 2500)

    @pytest.mark.asyncio
    async def test_r4_all_within_limits_passed(self):
        """R4: 全部合规，无 budget 打回 feedback。"""
        parsed, result = await review(
            raw_output=_make_plan(10000, BASE_BREAKDOWN),
            bundle=None,
            budget=10000,
            days=5,
            alloc=ALLOC,
        )
        assert result.passed is True
        assert result.code_checks.get("budget_items") == "ok"
        assert result.feedback == ""

    @pytest.mark.asyncio
    async def test_r5_missing_breakdown_keys_still_rejected(self):
        """R5: budgetBreakdown 缺字段（既有行为）在分项校验前打回。"""
        missing = {k: v for k, v in BASE_BREAKDOWN.items() if k != "tickets"}
        parsed, result = await review(
            raw_output=_make_plan(10000, missing),
            bundle=None,
            budget=10000,
            days=5,
            alloc=ALLOC,
        )
        assert result.passed is False
        assert result.code_checks.get("breakdown_complete") is False

    @pytest.mark.asyncio
    async def test_r6_total_ratio_guard_kept_without_alloc(self):
        """R6: 总和 >1.15 兜底（不传 alloc 时也生效）。"""
        parsed, result = await review(
            raw_output=_make_plan(12000, BASE_BREAKDOWN),
            bundle=None,
            budget=10000,
            days=5,
        )
        assert result.passed is False
        assert result.code_checks.get("budget_ratio") == 1.2

    @pytest.mark.asyncio
    async def test_r7_llm_review_warning_does_not_reject(self):
        """R7: LLM 层发现的问题只记 warning 不强制打回。"""
        with patch("src.services.agent.review._llm_review", return_value=["节奏不合理"]):
            parsed, result = await review(
                raw_output=_make_plan(10000, BASE_BREAKDOWN),
                bundle=None,
                budget=10000,
                days=5,
                alloc=ALLOC,
            )
        assert result.passed is True
        assert result.code_checks.get("llm_review") == ["节奏不合理"]
