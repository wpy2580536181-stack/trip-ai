"""T7 验收测试：knowledge_service 暴露价格 + estimator 接线（S2 系列 + E5 补充）。

链路：DB row(avg_cost) → search_spots dict → format_search_results 文本 → research_agent 提取 SpotItem。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.models.spot import Spot
from src.services.knowledge_service import KnowledgeService
from src.services.agent.schemas import CostSource, SpotItem


class TestRatingSearchExposesAvgCost:
    """S2a: _rating_search 检索返回 dict 含 avg_cost 键（真实 DB）。"""

    @pytest.mark.asyncio
    async def test_s2a_rating_search_returns_avg_cost(self, db_session):
        db_session.add_all([
            Spot(
                name="故宫", city="北京", category="attraction",
                description="皇家宫殿", tags=["历史"],
                avg_cost=60.0, rating=4.9,
            ),
            Spot(
                name="景山公园", city="北京", category="attraction",
                description="俯瞰紫禁城", tags=["公园"],
                avg_cost=None, rating=4.5,
            ),
        ])
        await db_session.commit()

        results = await KnowledgeService._rating_search(
            db_session, city="北京", category="attraction", limit=10,
        )

        assert len(results) == 2
        by_name = {r["name"]: r for r in results}
        assert "avg_cost" in by_name["故宫"]
        assert float(by_name["故宫"]["avg_cost"]) == 60.0
        assert by_name["景山公园"]["avg_cost"] is None


class TestFormatSearchResultsCost:
    """S2b/S2c: format_search_results 对 avg_cost 的展示/隐藏。"""

    async def _fmt(self, spot: dict) -> str:
        return await KnowledgeService.format_search_results([spot], include_details=True)

    @pytest.mark.asyncio
    async def test_s2b_no_cost_key_no_price_line(self):
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9,
        })
        assert "人均消费" not in text

    @pytest.mark.asyncio
    async def test_s2b_none_cost_no_price_line(self):
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9, "avg_cost": None,
        })
        assert "人均消费" not in text

    @pytest.mark.asyncio
    async def test_s2b_zero_cost_no_price_line(self):
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9, "avg_cost": 0,
        })
        assert "人均消费" not in text

    @pytest.mark.asyncio
    async def test_s2b_negative_cost_no_price_line(self):
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9, "avg_cost": -5,
        })
        assert "人均消费" not in text

    @pytest.mark.asyncio
    async def test_s2b_estimate_cost_not_shown(self):
        """防污染：enrich 后的估算价（cost_source=estimate）不进候选池文本。"""
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9,
            "avg_cost": 120, "cost_source": "estimate",
        })
        assert "人均消费" not in text

    @pytest.mark.asyncio
    async def test_s2c_cost_shown_as_yuan(self):
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9, "avg_cost": 60,
        })
        assert "人均消费：¥60" in text

    @pytest.mark.asyncio
    async def test_s2c_float_cost_formatted(self):
        text = await self._fmt({
            "name": "故宫", "city": "北京", "rating": 4.9, "avg_cost": 60.0,
        })
        assert "人均消费：¥60" in text
        assert "¥60.0" not in text


class TestExtractSpotItemsCost:
    """S2d: research_agent 从格式化文本提取 SpotItem 时透传 avg_cost。"""

    @staticmethod
    def _agent():
        return __import__(
            "src.services.agent.agents.research_agent",
            fromlist=["ResearchAgent"],
        ).ResearchAgent(llm=MagicMock())

    def test_s2d_extract_parses_cost_line(self):
        text = """找到 1 个相关景点：

1. 故宫（北京）
   - 评分：4.9 分
   - 人均消费：¥60
   - 介绍：皇家宫殿...
"""
        items = self._agent()._extract_spot_items(text, "attraction")
        assert len(items) == 1
        assert items[0].name == "故宫"
        assert items[0].avg_cost == 60.0
        assert items[0].cost_source is CostSource.RAG

    def test_s2d_extract_without_cost_line_keeps_none(self):
        text = """找到 1 个相关景点：

1. 景山公园（北京）
   - 评分：4.5 分
"""
        items = self._agent()._extract_spot_items(text, "attraction")
        assert items[0].name == "景山公园"
        assert items[0].avg_cost is None
        assert items[0].cost_source is None

    @pytest.mark.asyncio
    async def test_s2d_parallel_search_passes_cost_to_bundle(self, monkeypatch):
        """完整接线：工具返回含价格文本 → ResearchBundle.attraction_items 携带 avg_cost。"""
        from src.services.agent.agents.research_agent import ResearchAgent

        attraction_text = await KnowledgeService.format_search_results([
            {"id": "1", "name": "故宫", "city": "北京", "category": "attraction",
             "description": "皇家宫殿", "rating": 4.9, "tags": ["历史"],
             "avg_cost": 60.0, "_source": "rating"},
        ])
        food_text = await KnowledgeService.format_search_results([
            {"id": "2", "name": "全聚德", "city": "北京", "category": "food",
             "description": "烤鸭", "rating": 4.5, "tags": ["美食"],
             "avg_cost": 150, "_source": "rating"},
        ])

        class FakeRetrieveTool:
            """按 payload.category 返回对应分类文本，模拟真实工具的两次调用。"""

            def __init__(self, attraction_text, food_text):
                self._by_category = {"attraction": attraction_text, "food": food_text}

            async def ainvoke(self, payload):
                return self._by_category.get(payload.get("category"), "")

        monkeypatch.setattr(
            "src.services.agent.tools.retrieve_knowledge_tool",
            FakeRetrieveTool(attraction_text, food_text),
        )
        monkeypatch.setattr(
            "src.services.agent.tools.search_hotels_tool",
            FakeRetrieveTool(attraction_text, food_text),
        )
        monkeypatch.setattr(
            "src.services.mcp.amap_client.call_tool",
            AsyncMock(return_value="晴，25℃"),
        )

        agent = ResearchAgent(llm=MagicMock())
        bundle = await agent._parallel_search(
            city="北京", interests="", hotel_budget=200, departure_city=None,
        )

        assert isinstance(bundle.attraction_items[0], SpotItem)
        assert bundle.attraction_items[0].name == "故宫"
        assert bundle.attraction_items[0].avg_cost == 60.0
        assert bundle.attraction_items[0].cost_source is CostSource.RAG
        assert bundle.food_items[0].name == "全聚德"
        assert bundle.food_items[0].avg_cost == 150.0
        assert bundle.food_items[0].cost_source is CostSource.RAG
