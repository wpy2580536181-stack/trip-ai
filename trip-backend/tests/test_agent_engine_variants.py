"""AgentEngine.recommend_variants() 单测。

覆盖：
- recommend_variants 调用 orchestrator.plan_variants
- 返回 parsed_variants 数组
- Token 记录包含 variant_type
- 不破坏现有 recommend 方法
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.agent.agent_engine import AgentEngine
from src.services.agent.orchestrator import Orchestrator, PlanVariantsResult, VariantResult


@pytest.fixture
def agent_engine():
    return AgentEngine()


def _make_variant(variant_type: str, plan: dict | None = None) -> dict:
    return {
        "variant_type": variant_type,
        "label": f"test_{variant_type}",
        "plan": plan or {"city": "北京", "days": 3, "totalBudget": 5000,
                          "dailyItinerary": [{"day": 1, "morning": {"spot": "故宫"},
                                                              "afternoon": {"spot": "天安门"},
                                                              "evening": {"spot": "颐和园"}}],
                          "budgetBreakdown": {"accommodation": 1500, "food": 1200,
                                              "transportation": 1000, "tickets": 800, "other": 500},
                          "tips": [], "warnings": []},
        "raw_output": "raw",
        "review": None,
        "usage": {"prompt": 100, "completion": 50, "total": 150, "cached": 0},
        "duration_ms": 1000,
        "error": None,
    }


class TestRecommendVariants:
    """recommend_variants 方法验证。"""

    async def test_calls_plan_variants(self, agent_engine: AgentEngine):
        """recommend_variants 调用 orchestrator.plan_variants"""
        mock_result = PlanVariantsResult(
            variants=[VariantResult(variant_type="economy", label="test", plan={"city": "北京", "days": 3})],
            research_usage={},
            total_duration_ms=1000,
        )

        with patch.object(Orchestrator, "plan_variants", new_callable=AsyncMock, return_value=mock_result) as mock_plan_variants:
            result = await agent_engine.recommend_variants(
                user_id=1,
                city="北京",
                budget=5000,
                days=3,
            )
            mock_plan_variants.assert_called_once()

    async def test_returns_parsed_variants(self, agent_engine: AgentEngine):
        """返回 parsed_variants 数组，长度为 3"""
        mock_result = PlanVariantsResult(
            variants=[
                VariantResult(variant_type="economy", label="💰 经济型", plan={"city": "北京", "days": 3}),
                VariantResult(variant_type="comfort", label="⭐ 舒适型", plan={"city": "北京", "days": 3}),
                VariantResult(variant_type="photo", label="📸 打卡型", plan={"city": "北京", "days": 3}),
            ],
            research_usage={"prompt": 200},
            total_duration_ms=3000,
        )

        with patch.object(Orchestrator, "plan_variants", new_callable=AsyncMock, return_value=mock_result):
            result = await agent_engine.recommend_variants(
                user_id=1,
                city="北京",
                budget=5000,
                days=3,
            )

        assert "parsed_variants" in result
        assert len(result["parsed_variants"]) == 3
        assert result["parsed_variants"][0]["variant_type"] == "economy"
        assert result["parsed_variants"][1]["variant_type"] == "comfort"
        assert result["parsed_variants"][2]["variant_type"] == "photo"
        assert result["research_usage"] == {"prompt": 200}
        assert result["total_duration_ms"] == 3000

    async def test_token_record_contains_variant_type(self, agent_engine: AgentEngine):
        """Token 记录包含 variant_type 字段"""
        mock_result = PlanVariantsResult(
            variants=[
                VariantResult(
                    variant_type="economy",
                    label="💰 经济型",
                    plan={"city": "北京", "days": 3},
                    usage={"prompt": 100, "completion": 50, "total": 150, "cached": 0},
                    duration_ms=1000,
                ),
            ],
            research_usage={},
            total_duration_ms=1000,
        )

        with patch.object(Orchestrator, "plan_variants", new_callable=AsyncMock, return_value=mock_result):
            result = await agent_engine.recommend_variants(
                user_id=1,
                city="北京",
                budget=5000,
                days=3,
                message_id=42,
            )

        # 验证返回结构包含 variant 信息
        assert result["parsed_variants"][0]["variant_type"] == "economy"
        assert result["parsed_variants"][0]["label"] == "💰 经济型"
        assert result["parsed_variants"][0]["plan"] is not None

    async def test_empty_variants_returns_empty_list(self, agent_engine: AgentEngine):
        """空 variants 时返回空数组"""
        mock_result = PlanVariantsResult(
            variants=[],
            research_usage={},
            total_duration_ms=0,
        )

        with patch.object(Orchestrator, "plan_variants", new_callable=AsyncMock, return_value=mock_result):
            result = await agent_engine.recommend_variants(
                user_id=1,
                city="北京",
                budget=5000,
                days=3,
            )

        assert result["parsed_variants"] == []
        assert result["research_usage"] == {}
        assert result["total_duration_ms"] == 0
