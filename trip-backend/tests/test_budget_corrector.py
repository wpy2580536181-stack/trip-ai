"""corrector 测试。C1-C8 用例。"""
import copy
import dataclasses

import pytest

from src.services.agent.budget.corrector import build_correction
from src.services.agent.schemas import BudgetAllocation, CorrectorAction

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

PLAN = {
    "totalBudget": 12000,
    "budgetBreakdown": {
        "accommodation": 4000,
        "food": 2500,
        "transportation": 2000,
        "tickets": 3000,
        "other": 500,
    },
}


def _plan():
    return copy.deepcopy(PLAN)


def test_c1_round1_tightens_tickets_and_food():
    act = build_correction(_plan(), ALLOC, round=1)
    assert act.round == 1
    assert act.target_allocation == {
        "accommodation": 4000,
        "food": 2250,
        "transportation": 2000,
        "tickets": 600,
        "other": 500,
    }


def test_c2_round2_tightens_accommodation_only():
    act = build_correction(_plan(), ALLOC, round=2)
    assert act.round == 2
    assert act.target_allocation == {
        "accommodation": 2800,
        "food": 2500,
        "transportation": 2000,
        "tickets": 1000,
        "other": 500,
    }


def test_c3_round3_tightens_transportation_and_clears_other():
    act = build_correction(_plan(), ALLOC, round=3)
    assert act.round == 3
    assert act.target_allocation == {
        "accommodation": 4000,
        "food": 2500,
        "transportation": 1600,
        "tickets": 1000,
        "other": 0,
    }


def test_c4_over_amount_is_plan_total_minus_budget():
    act = build_correction(_plan(), ALLOC, round=1)
    assert act.over_amount == 2000


def test_c5_deterministic_same_input_same_output():
    a = build_correction(_plan(), ALLOC, round=2)
    b = build_correction(_plan(), ALLOC, round=2)
    assert dataclasses.asdict(a) == dataclasses.asdict(b)


def test_c6_round_above_3_falls_back_to_round3():
    act = build_correction(_plan(), ALLOC, round=4)
    base = build_correction(_plan(), ALLOC, round=3)
    assert dataclasses.asdict(act) == dataclasses.asdict(base)


def test_c7_instructions_contain_over_amount_and_target_amounts():
    act = build_correction(_plan(), ALLOC, round=1)
    assert "超支 2000 元" in act.instructions
    assert "门票目标 ≤ 600 元" in act.instructions
    assert "优先替换为免费景点" in act.instructions


def test_c8_no_side_effect_on_plan():
    plan = _plan()
    before = copy.deepcopy(plan)
    build_correction(plan, ALLOC, round=1)
    assert plan == before
