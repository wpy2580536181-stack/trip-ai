"""数据契约层测试：CostSource / BudgetAllocation / CorrectorAction / BudgetViolation + SpotItem 价格字段。

对应任务文档 tasks/budget-control-and-cost-fidelity-plan.md T1。
"""

import dataclasses

import pytest

from src.services.agent.schemas import (
    BudgetAllocation,
    BudgetViolation,
    BudgetViolationResult,
    CorrectorAction,
    CostSource,
    PlanResult,
    SpotItem,
)


class TestCostSource:
    def test_s4_enum_has_four_legal_values(self):
        """S4: 枚举包含 4 个合法值，MEITUAN 为预留值。"""
        assert {c.value for c in CostSource} == {
            "rag", "meituan", "estimate", "distance",
        }

    def test_s4_members_are_str_enum(self):
        assert CostSource.RAG == "rag"
        assert str(CostSource.ESTIMATE) == "CostSource.ESTIMATE"


class TestBudgetAllocation:
    def test_s1_default_construct(self):
        """S1: BudgetAllocation 可实例化。"""
        a = BudgetAllocation(budget=10000, days=5, style="comfort")
        assert a.budget == 10000
        assert a.days == 5
        assert a.style == "comfort"
        assert a.elasticity == 1.15

    def test_s1_asdict_roundtrip(self):
        """S1: asdict 序列化字段齐全。"""
        a = BudgetAllocation(budget=10000, days=5, style="comfort")
        d = dataclasses.asdict(a)
        assert set(d.keys()) == {
            "budget", "days", "style", "allocation",
            "daily_activity_limit", "elasticity",
        }
        assert d["allocation"] == {}


class TestCorrectorAction:
    def test_s1_default_keep_scope_is_full(self):
        """S1: CorrectorAction keep_scope 默认 'full'（为 P1 局部重生成预留）。"""
        act = CorrectorAction(
            round=1,
            over_amount=500,
            target_allocation={"tickets": 600, "food": 2700},
            instructions="测试指令",
        )
        assert act.keep_scope == "full"


class TestBudgetViolation:
    def test_violation_result_passed_default(self):
        v = BudgetViolation(key="tickets", actual=2000, limit=1200, over=800)
        assert v.over == 800
        r = BudgetViolationResult(violations=[v], over_amount=800)
        assert r.passed is False
        assert len(r.violations) == 1


class TestSpotItemCompatibility:
    def test_s3_legacy_construct_without_new_fields(self):
        """S3: 存量 SpotItem 构造（不传价格字段）不报错，新字段默认 None。"""
        item = SpotItem(name="西湖", category="attraction", rating=4.5)
        assert item.avg_cost is None
        assert item.cost_source is None

    def test_s5_spot_item_with_price_fields(self):
        item = SpotItem(name="故宫", category="attraction", avg_cost=60.0, cost_source=CostSource.RAG)
        assert item.avg_cost == 60.0
        assert item.cost_source == CostSource.RAG

    def test_s1_plan_result_asdict_compatible(self):
        """S1: PlanResult 序列化不因契约变化而抛异常。"""
        d = dataclasses.asdict(PlanResult())
        assert d["plan"] is None


@pytest.mark.skip(reason="预留：costSource 进入 plan dict 的 enrich 逻辑（T7 验收）")
def test_s2_placeholder():
    pass
