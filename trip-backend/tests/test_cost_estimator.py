"""cost_estimator 测试。E1-E7 用例。"""
from src.services.agent.budget.cost_estimator import CITY_TIER, estimate_cost, enrich_search_results
from src.services.agent.schemas import CostSource


class TestCostEstimator:
    def test_e1_spot_with_avg_cost_uses_rag(self):
        """E1: spot 有 avg_cost=120 → (120, CostSource.RAG)。"""
        amount, source = estimate_cost({"name": "故宫", "avg_cost": 120}, "high")
        assert amount == 120
        assert source is CostSource.RAG

    def test_e2_missing_cost_high_tier_attraction(self):
        """E2: 无 avg_cost + 城市 high 档 + attraction → (档位默认价, ESTIMATE)。"""
        amount, source = estimate_cost({"name": "故宫"}, "high", "attraction")
        assert amount == CITY_TIER["high"]["attraction"]
        assert source is CostSource.ESTIMATE

    def test_e3_city_tier_differs(self):
        """E3: 城市档位差异：high ≠ low 的同一类别默认价。"""
        assert CITY_TIER["high"]["attraction"] != CITY_TIER["low"]["attraction"]
        amount_high, _ = estimate_cost({"name": "故宫"}, "high", "attraction")
        amount_low, _ = estimate_cost({"name": "故宫"}, "low", "attraction")
        assert amount_high != amount_low

    def test_e4_category_differs(self):
        """E4: 类别差异：attraction ≠ hotel_night 默认价。"""
        assert CITY_TIER["high"]["attraction"] != CITY_TIER["high"]["hotel_night"]
        amount_attr, _ = estimate_cost({"name": "故宫"}, "high", "attraction")
        amount_hotel, _ = estimate_cost({"name": "故宫"}, "high", "hotel_night")
        assert amount_attr != amount_hotel

    def test_e5_enrich_adds_keys_with_correct_types(self):
        """E5: enrich 后每条 dict 含 avg_cost 与 cost_source 键，值类型正确。"""
        results = [{"name": "景点A"}, {"name": "景点B", "avg_cost": 90}]
        enriched = enrich_search_results(results, "high")
        assert len(enriched) == 2
        for item, orig in zip(enriched, results):
            assert "avg_cost" in item and "cost_source" in item
            assert isinstance(item["avg_cost"], int)
            assert isinstance(item["cost_source"], str)
            assert item is not orig
        assert enriched[0]["avg_cost"] == CITY_TIER["high"]["attraction"]
        assert enriched[0]["cost_source"] == CostSource.ESTIMATE.value
        assert enriched[1]["avg_cost"] == 90
        assert enriched[1]["cost_source"] == CostSource.RAG.value
        assert "avg_cost" not in results[0] and "cost_source" not in results[0]

    def test_e6_deterministic(self):
        """E6: 确定性：同输入两次输出相同。"""
        results = [{"name": "景点A"}, {"name": "景点B", "avg_cost": 90}]
        first = enrich_search_results(results, "medium")
        second = enrich_search_results(results, "medium")
        assert first == second
        assert estimate_cost({"name": "故宫"}, "high") == estimate_cost({"name": "故宫"}, "high")

    def test_e7_zero_avg_cost_treated_as_missing(self):
        """E7: avg_cost=0 视为缺失 → 走 ESTIMATE。"""
        amount, source = estimate_cost({"name": "故宫", "avg_cost": 0}, "low", "attraction")
        assert source is CostSource.ESTIMATE
        assert amount == CITY_TIER["low"]["attraction"]
