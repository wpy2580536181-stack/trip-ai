"""orchestrator 预算修正循环测试。O1-O6 用例。

覆盖：
- O1 行程超支 → 重试循环注入 budget_correction（round=1）
- O2 修正后收敛：最终返回 plan 且 review passed
- O3 多轮仍不收敛：不崩溃，记录 warning 后照常返回（带 issues）
- O4 预算内行程：budget_correction 从未注入，corrector 未被调用
- O5 variants 各 variant 独立修正，且 review 收到共享 alloc
- O6 allocator 接线正确：review 被调用时带 alloc，allocation 5 项齐全
"""

from __future__ import annotations

import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent.agents.planner_agent import PlannerAgent
from src.services.agent.agents.research_agent import ResearchAgent
from src.services.agent.orchestrator import Orchestrator
from src.services.agent.review import review as real_review
from src.services.agent.schemas import CorrectorAction, PlanRequest, ResearchBundle

BUDGET = 10000
DAYS = 5

# comfort 分配：accommodation 4000 / food 2500 / transportation 2000 / tickets 1000 / other 500
# 弹性 1.15 → tickets 上限 1150，其余类似


def _make_itinerary() -> list[dict]:
    return [
        {
            "day": i,
            "morning": {"spot": f"景点{i}-a"},
            "afternoon": {"spot": f"景点{i}-b"},
            "evening": {"spot": f"景点{i}-c"},
        }
        for i in range(1, DAYS + 1)
    ]


# 合规行程：各分项 ≤ 上限×1.15，总预算 ≤ budget×1.15，5 天
OK_PLAN = {
    "city": "北京",
    "days": DAYS,
    "totalBudget": BUDGET,
    "dailyItinerary": _make_itinerary(),
    "budgetBreakdown": {
        "accommodation": 4000,
        "food": 2500,
        "transportation": 2000,
        "tickets": 1000,
        "other": 500,
    },
    "tips": ["tip"],
    "warnings": [],
}

# 超支行程：tickets 3000 > 1150（分项违规打回）；totalBudget 11000 ≤ 11500（总预算检查放行）
OVER_PLAN = {
    "city": "北京",
    "days": DAYS,
    "totalBudget": 11000,
    "dailyItinerary": _make_itinerary(),
    "budgetBreakdown": {
        "accommodation": 3500,
        "food": 2500,
        "transportation": 1500,
        "tickets": 3000,
        "other": 500,
    },
    "tips": ["tip"],
    "warnings": [],
}

OK_JSON = json.dumps(OK_PLAN, ensure_ascii=False)
OVER_JSON = json.dumps(OVER_PLAN, ensure_ascii=False)


def _make_research_ok() -> MagicMock:
    return MagicMock(
        error=None,
        result=ResearchBundle(),
        usage={"prompt": 0, "completion": 0, "total": 0, "cached": 0},
        duration_ms=10,
    )


def _make_planner_output(json_str: str) -> MagicMock:
    return MagicMock(
        error=None,
        result=json_str,
        usage={"prompt": 100, "completion": 50, "total": 150, "cached": 0},
        duration_ms=100,
    )


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(llm=MagicMock())


@pytest.fixture
def plan_request() -> PlanRequest:
    return PlanRequest(user_id=1, city="北京", days=DAYS, budget=BUDGET)


class TestBudgetCorrectionLoop:
    """plan() 预算修正重试循环。"""

    async def test_o1_retry_injects_budget_correction(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """O1: 超支 → 第二次 planner_input 注入 budget_correction（round=1）"""
        planner_inputs: list = []

        async def _planner(planner_input):
            # orchestrator 重试时复用同一 PlannerInput 实例，捕获浅拷贝以区分轮次
            planner_inputs.append(copy.copy(planner_input))
            if len(planner_inputs) == 1:
                return _make_planner_output(OVER_JSON)
            return _make_planner_output(OK_JSON)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_ok()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner), \
             patch("src.services.agent.review._llm_review", new_callable=AsyncMock, return_value=[]):
            result = await orchestrator.plan(plan_request)

        assert len(planner_inputs) == 2
        assert planner_inputs[0].budget_correction is None
        corr = planner_inputs[1].budget_correction
        assert corr is not None
        assert isinstance(corr, CorrectorAction)
        assert corr.round == 1
        assert corr.over_amount == 1000
        assert result.plan is not None
        assert result.review is not None
        assert result.review.passed

    async def test_o2_converges_after_correction(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """O2: 修正后收敛 → 返回合规 plan 且 review passed"""
        planner_inputs: list = []

        async def _planner(planner_input):
            planner_inputs.append(copy.copy(planner_input))
            if len(planner_inputs) == 1:
                return _make_planner_output(OVER_JSON)
            return _make_planner_output(OK_JSON)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_ok()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner), \
             patch("src.services.agent.review._llm_review", new_callable=AsyncMock, return_value=[]):
            result = await orchestrator.plan(plan_request)

        assert result.review is not None and result.review.passed
        assert result.plan is not None
        assert result.plan["totalBudget"] == BUDGET
        assert result.plan["budgetBreakdown"]["tickets"] <= 1150
        assert result.review.code_checks.get("budget_items") == "ok"

    async def test_o3_gives_up_after_max_retries(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """O3: 始终超支 → 不崩溃，多轮注入 correction 后按现有失败行为返回（带 issues）"""
        planner_inputs: list = []

        async def _planner(planner_input):
            planner_inputs.append(copy.copy(planner_input))
            return _make_planner_output(OVER_JSON)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_ok()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner), \
             patch("src.services.agent.review._llm_review", new_callable=AsyncMock, return_value=[]):
            result = await orchestrator.plan(plan_request)

        assert len(planner_inputs) == 3  # 初始 + 2 轮重试
        assert result.review is not None
        assert result.review.passed is False
        assert len(result.review.issues) > 0
        # 每轮重试都注入 correction，round 递增
        corrs = [p.budget_correction for p in planner_inputs[1:]]
        assert all(c is not None for c in corrs)
        assert [c.round for c in corrs] == [1, 2]

    async def test_o4_no_correction_when_within_budget(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """O4: 预算内行程 → budget_correction 从未注入，corrector 未被调用"""
        planner_inputs: list = []

        async def _planner(planner_input):
            planner_inputs.append(planner_input)
            return _make_planner_output(OK_JSON)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_ok()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner), \
             patch("src.services.agent.review._llm_review", new_callable=AsyncMock, return_value=[]), \
             patch("src.services.agent.orchestrator.build_correction") as mock_corr:
            result = await orchestrator.plan(plan_request)

        assert mock_corr.call_count == 0
        assert len(planner_inputs) == 1
        assert all(p.budget_correction is None for p in planner_inputs)
        assert result.review is not None and result.review.passed


class TestVariantsBudgetCorrection:
    """plan_variants() 预算修正接入。"""

    async def test_o5_variants_inject_correction_independently(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """O5: 各 variant 独立重试注入 correction，且 review 收到共享 alloc"""
        captured_inputs: list = []
        per_variant = {"economy": 0, "comfort": 0, "photo": 0}
        review_kwargs: list[dict] = []

        async def _planner(planner_input):
            captured_inputs.append(copy.copy(planner_input))
            vt = planner_input.variant_type
            per_variant[vt] += 1
            if per_variant[vt] == 1:
                return _make_planner_output(OVER_JSON)
            return _make_planner_output(OK_JSON)

        async def _spy_review(*args, **kwargs):
            review_kwargs.append(kwargs)
            return await real_review(*args, **kwargs)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_ok()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner), \
             patch("src.services.agent.orchestrator.review", side_effect=_spy_review), \
             patch("src.services.agent.review._llm_review", new_callable=AsyncMock, return_value=[]):
            result = await orchestrator.plan_variants(plan_request)

        assert len(result.variants) == 3
        assert all(v.plan is not None for v in result.variants)
        assert all(v.review is not None and v.review.passed for v in result.variants)

        # 每个 variant：第一次无 correction，第二次注入 round=1
        by_variant: dict[str, list] = {}
        for pi in captured_inputs:
            by_variant.setdefault(pi.variant_type, []).append(pi)
        assert set(by_variant) == {"economy", "comfort", "photo"}
        for vt in ("economy", "comfort", "photo"):
            inputs = by_variant[vt]
            assert len(inputs) == 2, f"{vt} 应重试一次"
            assert inputs[0].budget_correction is None
            assert inputs[1].budget_correction is not None
            assert inputs[1].budget_correction.round == 1

        # 每次 review（6 次）都收到共享 alloc
        assert len(review_kwargs) == 6
        allocs = {id(kw.get("alloc")) for kw in review_kwargs}
        assert len(allocs) == 1  # 同一实例共享
        alloc = review_kwargs[0]["alloc"]
        assert alloc is not None
        assert set(alloc.allocation) == {"accommodation", "food", "transportation", "tickets", "other"}


class TestAllocatorWiring:
    """allocator 接线验证。"""

    async def test_o6_review_receives_alloc(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """O6: review 被调用时带 alloc，allocation 5 项齐全"""
        review_kwargs: list[dict] = []

        async def _planner(planner_input):
            return _make_planner_output(OK_JSON)

        async def _spy_review(*args, **kwargs):
            review_kwargs.append(kwargs)
            return await real_review(*args, **kwargs)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_ok()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner), \
             patch("src.services.agent.orchestrator.review", side_effect=_spy_review), \
             patch("src.services.agent.review._llm_review", new_callable=AsyncMock, return_value=[]):
            await orchestrator.plan(plan_request)

        assert len(review_kwargs) == 1
        alloc = review_kwargs[0].get("alloc")
        assert alloc is not None
        assert alloc.budget == BUDGET
        assert alloc.days == DAYS
        assert set(alloc.allocation) == {"accommodation", "food", "transportation", "tickets", "other"}
        assert all(v > 0 for v in alloc.allocation.values())
