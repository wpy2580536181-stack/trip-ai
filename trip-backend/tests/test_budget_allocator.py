"""allocator 测试。A1-A8 用例。"""
from src.services.agent.budget.allocator import allocate


class TestAllocator:
    def test_a1_comfort_default_10000_5d(self):
        """A1: 默认 comfort 中档 10000/5天 五项分解。"""
        result = allocate(budget=10000, days=5)
        assert result.allocation["accommodation"] == 4000
        assert result.allocation["food"] == 2500
        assert result.allocation["transportation"] == 2000
        assert result.allocation["tickets"] == 1000
        assert result.allocation["other"] == 500
        assert abs(sum(result.allocation.values()) - 10000) <= 500

    def test_a2_budget_style(self):
        """A2: budget 风格 accommodation=35%、tickets=15%、food=30%。"""
        result = allocate(budget=10000, days=5, style="budget")
        assert result.allocation["accommodation"] == 3500
        assert result.allocation["tickets"] == 1500
        assert result.allocation["food"] == 3000

    def test_a3_luxury_style(self):
        """A3: luxury 风格 accommodation=50%。"""
        result = allocate(budget=10000, days=5, style="luxury")
        assert result.allocation["accommodation"] == 5000

    def test_a4_low_budget_fallback(self):
        """A4: 预算 ≤2000 时 tickets=15%、food 上浮到 30%。"""
        result = allocate(budget=2000, days=2, style="comfort")
        assert result.allocation["tickets"] == 300
        assert result.allocation["food"] == 600

    def test_a5_deterministic(self):
        """A5: 同输入两次结果 deep-equal。"""
        assert allocate(budget=10000, days=5) == allocate(budget=10000, days=5)

    def test_a6_daily_activity_limit(self):
        """A6: daily_activity_limit = round10(budget/days×0.30)。"""
        result = allocate(budget=10000, days=5)
        assert result.daily_activity_limit == 600

    def test_a7_budget_50_edge(self):
        """A7: 边界 budget=50 全字段 ≥0 且不抛异常。"""
        result = allocate(budget=50, days=1)
        for key, value in result.allocation.items():
            assert value >= 0, f"{key} 为负: {value}"

    def test_a8_elasticity_default_and_override(self):
        """A8: elasticity 默认 1.15，可覆盖。"""
        assert allocate(budget=10000, days=5).elasticity == 1.15
        assert allocate(budget=10000, days=5, elasticity=1.5).elasticity == 1.5
