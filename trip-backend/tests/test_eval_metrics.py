"""eval_metrics 指标计算逻辑验证（不依赖后端，纯函数测试）。"""

from __future__ import annotations

import pytest

from scripts.eval_metrics import (
    MetricResult,
    SlotCost,
    TripMetrics,
    _m1_cost_source_coverage,
    _m2_ticket_rag_ratio,
    _m3_budget_convergence,
)


def _make_trip(slots: list[SlotCost], budget: int = 10000, total: int = 10000, rounds: int = 1, converged: bool = True) -> TripMetrics:
    return TripMetrics(
        trip_id="t1",
        city="成都",
        budget=budget,
        total_budget=total,
        slots=slots,
        breakdown={},
        review_rounds=rounds,
        converged=converged,
    )


class TestM1CostSourceCoverage:
    def test_all_covered(self):
        slots = [SlotCost("故宫", "attraction", 100, "rag")] * 10
        r = _m1_cost_source_coverage([_make_trip(slots)])
        assert r.actual == 1.0
        assert r.passed is True
        assert r.threshold == 0.90

    def test_below_threshold(self):
        """8 有来源 + 2 无来源 → 8/10 = 80%，低于 90% → FAIL。"""
        slots = [SlotCost("故宫", "attraction", 100, "rag")] * 8 + [SlotCost("西湖", "attraction", 0, "")] * 2
        r = _m1_cost_source_coverage([_make_trip(slots)])
        assert r.actual == pytest.approx(0.8)
        assert r.passed is False
        assert "8/10" in r.detail

    def test_empty(self):
        r = _m1_cost_source_coverage([_make_trip([])])
        assert r.passed is False
        assert r.actual == 0.0


class TestM2TicketRagRatio:
    def test_high_rag(self):
        """10 个门票类 slot（7 RAG + 3 ESTIMATE）→ 70%。"""
        slots = [SlotCost("故宫", "ticket", 100, "rag")] * 7 + [SlotCost("西湖", "ticket", 50, "estimate")] * 3
        r = _m2_ticket_rag_ratio([_make_trip(slots)])
        assert r.actual == pytest.approx(0.7)
        assert r.passed is True

    def test_low_rag(self):
        """5 个门票 ESTIMATE + 5 个非门票 RAG → 门票 RAG=0%。"""
        slots = [SlotCost("故宫", "ticket", 100, "estimate")] * 5 + [SlotCost("小吃", "food", 50, "rag")] * 5
        r = _m2_ticket_rag_ratio([_make_trip(slots)])
        assert r.actual == 0.0
        assert r.passed is False

    def test_no_ticket(self):
        """全 food slot → 无门票数据。"""
        slots = [SlotCost("小吃", "food", 50, "estimate")]
        r = _m2_ticket_rag_ratio([_make_trip(slots)])
        assert r.passed is False
        assert "无门票数据" in r.detail


class TestM3BudgetConvergence:
    def test_all_converged(self):
        slots = [SlotCost("故宫", "ticket", 100, "rag")] * 5
        trips = [_make_trip(slots, total=11000, rounds=2, converged=True) for _ in range(5)]
        r = _m3_budget_convergence(trips, mode="mock")
        assert r.actual == 1.0
        assert r.passed is True

    def test_half_converged(self):
        slots = [SlotCost("故宫", "ticket", 100, "rag")] * 5
        trips = [
            _make_trip(slots, total=12000, rounds=1 if i < 5 else 3, converged=i < 5)
            for i in range(10)
        ]
        r = _m3_budget_convergence(trips, mode="mock")
        assert r.actual == 0.5
        assert r.passed is False

    def test_no_overbudget_mock(self):
        """无超支 → 全收敛，detail 含 mock 提示。"""
        slots = [SlotCost("故宫", "ticket", 100, "rag")] * 5
        r = _m3_budget_convergence([_make_trip(slots, total=9000)], mode="mock")
        assert r.actual == 1.0
        assert r.passed is True
        # mock 模式 hint
        assert "mock" in r.detail.lower() or "无超支" in r.detail

    def test_detail_contains_stats(self):
        slots = [SlotCost("故宫", "ticket", 100, "rag")] * 5
        trips = [
            _make_trip(slots, total=12000, rounds=1, converged=True),
            _make_trip(slots, total=15000, rounds=3, converged=False),
        ]
        r = _m3_budget_convergence(trips, mode="mock")
        assert "1/2" in r.detail
        assert r.actual == 0.5
