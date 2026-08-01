"""TripService.recommend() 多 variant 集成测试。

覆盖：
- recommend() 调用 recommend_variants()
- 每个 variant 持久化为 status="candidate" 的 Trip
- 返回 data.variants 数组
- _build_variant_summary 正确提取 spotCount / highlights
- 降级：空 variants 时抛 ValueError
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent.orchestrator import PlanVariantsResult, VariantResult
from src.services.trip_service import TripService


def _make_variant(variant_type: str, budget: int = 5000) -> dict:
    return {
        "variant_type": variant_type,
        "label": f"test_{variant_type}",
        "plan": {
            "city": "北京",
            "days": 3,
            "totalBudget": budget,
            "dailyItinerary": [
                {"day": 1, "morning": {"spot": "故宫"}, "afternoon": {"spot": "天安门"}, "evening": {"spot": "颐和园"}},
                {"day": 2, "morning": {"spot": "长城"}, "afternoon": {"spot": "鸟巢"}, "evening": {"spot": "三里屯"}},
                {"day": 3, "morning": {"spot": "颐和园"}, "afternoon": {"spot": "圆明园"}, "evening": {"spot": "南锣鼓巷"}},
            ],
            "budgetBreakdown": {"accommodation": 1500, "food": 1200, "transportation": 1000, "tickets": 800, "other": 500},
            "tips": [f"{variant_type} tips"], "warnings": [],
        },
        "raw_output": "raw",
        "review": None,
        "usage": {"prompt": 100, "completion": 50, "total": 150, "cached": 0},
        "duration_ms": 1000,
        "error": None,
    }


@pytest.fixture
def trip_service():
    return TripService()


class TestRecommendVariantsIntegration:
    """recommend() 多 variant 集成验证。"""

    async def test_calls_recommend_variants(self, trip_service: TripService):
        """recommend() 调用 agent_engine.recommend_variants()"""
        mock_result = {
            "parsed_variants": [_make_variant("economy")],
            "research_usage": {},
            "total_duration_ms": 1000,
        }

        with patch("src.services.trip_service.get_agent_engine") as mock_engine, \
             patch("src.services.trip_service.trip_log"), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock, return_value=1):
            mock_engine.return_value.recommend_variants = AsyncMock(return_value=mock_result)
            result = await trip_service.recommend(
                city="北京", budget=5000, days=3, user_id=1,
            )
            mock_engine.return_value.recommend_variants.assert_called_once()

    async def test_returns_variants_in_response(self, trip_service: TripService):
        """响应包含 variants 数组"""
        mock_result = {
            "parsed_variants": [
                _make_variant("economy", budget=3000),
                _make_variant("comfort", budget=5000),
                _make_variant("photo", budget=7000),
            ],
            "research_usage": {},
            "total_duration_ms": 3000,
        }

        with patch("src.services.trip_service.get_agent_engine") as mock_engine, \
             patch("src.services.trip_service.trip_log"), \
             patch.object(TripService, "_persist_trip", new_callable=AsyncMock, side_effect=[101, 102, 103]):
            mock_engine.return_value.recommend_variants = AsyncMock(return_value=mock_result)
            result = await trip_service.recommend(
                city="北京", budget=5000, days=3, user_id=1,
            )

        assert result["success"] is True
        assert "variants" in result["data"]
        assert len(result["data"]["variants"]) == 3
        assert result["data"]["variants"][0]["variantType"] == "economy"
        assert result["data"]["variants"][0]["tripId"] == 101
        assert result["data"]["variants"][1]["variantType"] == "comfort"
        assert result["data"]["variants"][1]["tripId"] == 102
        assert result["data"]["variants"][2]["variantType"] == "photo"
        assert result["data"]["variants"][2]["tripId"] == 103

    async def test_empty_variants_raises(self, trip_service: TripService):
        """空 variants → ValueError"""
        mock_result = {
            "parsed_variants": [],
            "research_usage": {},
            "total_duration_ms": 0,
        }

        with patch("src.services.trip_service.get_agent_engine") as mock_engine, \
             patch("src.services.trip_service.trip_log"):
            mock_engine.return_value.recommend_variants = AsyncMock(return_value=mock_result)
            with pytest.raises(ValueError, match="行程推荐失败"):
                await trip_service.recommend(
                    city="北京", budget=5000, days=3, user_id=1,
                )


class TestBuildVariantSummary:
    """_build_variant_summary() 摘要提取验证。"""

    async def test_spot_count_correct(self, trip_service: TripService):
        """spotCount 正确统计 morning/afternoon/evening 非空景点数"""
        variant = _make_variant("economy")
        summary = trip_service._build_variant_summary(variant, trip_id=1)
        # 3 天 × 3 时段 = 9 个景点
        assert summary["spotCount"] == 9

    async def test_highlights_extract_first_morning(self, trip_service: TripService):
        """highlights 取前 2 天上午的景点"""
        variant = _make_variant("economy")
        summary = trip_service._build_variant_summary(variant, trip_id=1)
        assert summary["highlights"] == ["故宫", "长城"]

    async def test_trip_id_set(self, trip_service: TripService):
        """tripId 正确设置"""
        variant = _make_variant("economy")
        summary = trip_service._build_variant_summary(variant, trip_id=42)
        assert summary["tripId"] == 42

    async def test_budget_from_plan(self, trip_service: TripService):
        """totalBudget 从 plan 中提取"""
        variant = _make_variant("economy", budget=3000)
        summary = trip_service._build_variant_summary(variant, trip_id=1)
        assert summary["totalBudget"] == 3000

    async def test_empty_plan_handles_gracefully(self, trip_service: TripService):
        """plan 为空时降级处理"""
        variant = {"variant_type": "economy", "label": "test", "plan": {}}
        summary = trip_service._build_variant_summary(variant, trip_id=1)
        assert summary["spotCount"] == 0
        assert summary["highlights"] == []
        assert summary["totalBudget"] == 0
