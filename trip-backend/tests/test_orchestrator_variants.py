"""Orchestrator.plan_variants() 单测。

覆盖：
- 返回 3 个 VariantResult（economy/comfort/photo）
- ResearchAgent 只调用 1 次
- PlannerAgent 调用 3 次
- 任一 Planner 失败不影响其他
- Review 循环：失败后重试，MAX_REVIEW_RETRIES 后仍失败则 plan=None
- Progress 事件包含 variant 字段
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent.agents.planner_agent import PlannerAgent
from src.services.agent.agents.research_agent import ResearchAgent
from src.services.agent.orchestrator import Orchestrator
from src.services.agent.schemas import (
    PlanRequest,
    PlanVariantsResult,
    ReviewResult,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模块级辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _make_review(passed: bool, feedback: str = "") -> ReviewResult:
    return ReviewResult(passed=passed, issues=[] if passed else ["issue"], feedback=feedback)


def _make_plan_json(variant_type: str = "", budget: int = 5000) -> str:
    return json.dumps({
        "city": "北京",
        "days": 3,
        "totalBudget": budget,
        "dailyItinerary": [
            {"day": 1, "morning": {"spot": "故宫"}, "afternoon": {"spot": "天安门"}, "evening": {"spot": "颐和园"}},
        ],
        "budgetBreakdown": {"accommodation": 1500, "food": 1200, "transportation": 1000, "tickets": 800, "other": 500},
        "tips": [f"{variant_type} tips"] if variant_type else [],
        "warnings": [],
    })


def _make_planner_ok(variant_type: str = "", budget: int = 5000) -> MagicMock:
    return MagicMock(error=None, result=_make_plan_json(variant_type, budget),
                     usage={"prompt": 100, "completion": 50, "total": 150, "cached": 0}, duration_ms=1000)


def _make_planner_err(msg: str = "planner failed") -> MagicMock:
    return MagicMock(error=msg, result=None, usage={}, duration_ms=0)


def _make_research_ok() -> MagicMock:
    return MagicMock(error=None, result=None, usage={}, duration_ms=100)


def _make_research_bundle() -> MagicMock:
    from src.services.agent.schemas import ResearchBundle
    return MagicMock(error=None, result=ResearchBundle(
        attractions="景点：故宫、天安门、颐和园",
        food="美食：烤鸭、炸酱面",
        hotels="酒店：王府井酒店",
    ), usage={}, duration_ms=100)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Fixtures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.fixture
def orchestrator():
    return Orchestrator(llm=MagicMock())


@pytest.fixture
def plan_request():
    return PlanRequest(user_id=1, city="北京", days=3, budget=5000)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestPlanVariantsBasic:
    """基础场景：3 个 variant 全部成功生成。"""

    async def test_returns_three_variants(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """BE-01: plan_variants() 返回 3 个 VariantResult，类型为 economy/comfort/photo"""
        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_bundle()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, return_value=_make_planner_ok()), \
             patch("src.services.agent.orchestrator.review", return_value=(True, _make_review(passed=True))):
            result: PlanVariantsResult = await orchestrator.plan_variants(plan_request)

        assert len(result.variants) == 3
        types = [v.variant_type for v in result.variants]
        assert types == ["economy", "comfort", "photo"]

    async def test_research_called_once(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """BE-02: ResearchAgent 只调用 1 次"""
        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_bundle()) as mock_res, \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, return_value=_make_planner_ok()), \
             patch("src.services.agent.orchestrator.review", return_value=(True, _make_review(passed=True))):
            await orchestrator.plan_variants(plan_request)
            assert mock_res.call_count == 1

    async def test_planner_called_three_times(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """BE-03: PlannerAgent 调用 3 次（每个 variant 一次）"""
        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_bundle()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, return_value=_make_planner_ok()) as mock_planner, \
             patch("src.services.agent.orchestrator.review", return_value=(True, _make_review(passed=True))):
            await orchestrator.plan_variants(plan_request)
            assert mock_planner.call_count == 3

    async def test_one_planner_failure_does_not_affect_others(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """BE-03（降级）: 任一 Planner 失败不影响其他 variant"""

        async def _planner_side_effect(planner_input):
            vtype = getattr(planner_input, "variant_type", "")
            if vtype == "comfort":
                return _make_planner_err("comfort failed")
            return _make_planner_ok(vtype)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_bundle()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner_side_effect), \
             patch("src.services.agent.orchestrator.review", return_value=(True, _make_review(passed=True))):
            result: PlanVariantsResult = await orchestrator.plan_variants(plan_request)

        assert len(result.variants) == 3
        assert result.variants[0].plan is not None
        assert result.variants[1].error == "comfort failed"
        assert result.variants[1].plan is None
        assert result.variants[2].plan is not None


class TestPlanVariantsReview:
    """Review 循环逻辑。"""

    async def test_review_retry_success(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """Review 第一次失败 + feedback 重跑 Planner → 第二次通过"""
        review_calls = {"count": 0}

        async def _planner_side_effect(planner_input):
            return _make_planner_ok(getattr(planner_input, "variant_type", ""))

        async def _review_side_effect(*args, **kwargs):
            review_calls["count"] += 1
            if review_calls["count"] == 1:
                return False, _make_review(passed=False, feedback="请调整预算")
            return True, _make_review(passed=True)

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_bundle()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner_side_effect), \
             patch("src.services.agent.orchestrator.review", side_effect=_review_side_effect):
            result: PlanVariantsResult = await orchestrator.plan_variants(plan_request)

        economy = next(v for v in result.variants if v.variant_type == "economy")
        assert economy.plan is not None
        # economy 触发 2 次 review（初始 failed + retry passed），其他 variant 各 1 次
        assert review_calls["count"] == 4  # economy: 2, comfort: 1, photo: 1

    async def test_review_max_retries_failure(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """Review 连续 MAX_REVIEW_RETRIES 次失败 → 该 variant plan 为 None"""
        async def _planner_side_effect(planner_input):
            return _make_planner_ok(getattr(planner_input, "variant_type", ""))

        async def _review_side_effect(*args, **kwargs):
            return None, _make_review(passed=False, feedback="始终不通过")

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, return_value=_make_research_bundle()), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_planner_side_effect), \
             patch("src.services.agent.orchestrator.review", side_effect=_review_side_effect):
            result: PlanVariantsResult = await orchestrator.plan_variants(plan_request)

        economy = next(v for v in result.variants if v.variant_type == "economy")
        assert economy.plan is None
        assert economy.error is None


class TestPlanVariantsProgress:
    """Progress 事件验证。"""

    async def test_progress_events_contain_variant_field(self, orchestrator: Orchestrator, plan_request: PlanRequest):
        """plan/review 的 progress 事件必须包含 variant 字段"""
        events: list[dict] = []

        async def on_event(event: dict):
            events.append(event)

        orchestrator.on_event = on_event

        async def _mock_research(*args, **kwargs):
            return _make_research_bundle()

        async def _mock_planner(*args, **kwargs):
            return _make_planner_ok()

        with patch.object(ResearchAgent, "run", new_callable=AsyncMock, side_effect=_mock_research), \
             patch.object(PlannerAgent, "run", new_callable=AsyncMock, side_effect=_mock_planner), \
             patch("src.services.agent.orchestrator.review", return_value=(True, _make_review(passed=True))):
            await orchestrator.plan_variants(plan_request)

        plan_events = [e for e in events if e.get("type") == "progress" and e.get("data", {}).get("stage") == "plan"]
        # 每个 variant 产生 start + done 两个 plan 事件
        assert len(plan_events) >= 3
        variants_seen = set()
        for ev in plan_events:
            assert "variant" in ev.get("data", {}), f"plan event missing variant field: {ev}"
            variants_seen.add(ev["data"]["variant"])
        assert variants_seen == {"economy", "comfort", "photo"}

        review_events = [e for e in events if e.get("type") == "progress" and e.get("data", {}).get("stage") == "review"]
        # 每个 variant 产生 start + done 两个 review 事件
        assert len(review_events) >= 3
        review_variants_seen = set()
        for ev in review_events:
            assert "variant" in ev.get("data", {}), f"review event missing variant field: {ev}"
            review_variants_seen.add(ev["data"]["variant"])
        assert review_variants_seen == {"economy", "comfort", "photo"}
