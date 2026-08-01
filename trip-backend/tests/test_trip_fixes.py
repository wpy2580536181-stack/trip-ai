"""Tests for trip-197 bug fixes: deduplication, time-slot isolation, pool compliance."""

import pytest
from unittest.mock import MagicMock, patch

from src.services.trip_service import TripService
from src.services.agent.agents.research_agent import ResearchAgent
from src.services.agent.review import review
from src.services.agent.schemas import ResearchBundle, SpotItem


# ---------------------------------------------------------------------------
# Test 1: _validate_and_fix_trip_data — 跨天去重
# ---------------------------------------------------------------------------

class TestValidateAndFixTripData:
    """Test suite for _validate_and_fix_trip_data deduplication and time-slot fixes."""

    def test_cross_day_deduplication(self):
        """同一景点出现在多天时，后续重复的应被清空。"""
        parsed = {
            "dailyItinerary": [
                {
                    "day": 1,
                    "morning": {"spot": "天安门", "duration": "2h"},
                    "afternoon": {"spot": "故宫", "duration": "3h"},
                    "evening": {"spot": "景山", "duration": "1h"},
                },
                {
                    "day": 2,
                    "morning": {"spot": "天安门", "duration": "2h"},  # 重复，应被清空
                    "afternoon": {"spot": "颐和园", "duration": "3h"},
                    "evening": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                },
                {
                    "day": 3,
                    "morning": {"spot": "天安门", "duration": "2h"},  # 重复，应被清空
                    "afternoon": {"spot": "圆明园", "duration": "3h"},
                    "evening": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                },
            ]
        }

        TripService._validate_and_fix_trip_data(parsed)

        itinerary = parsed["dailyItinerary"]
        # Day 1: 天安门 应保留（首次出现）
        assert itinerary[0]["morning"]["spot"] == "天安门"
        # Day 2: 天安门 应被清空
        assert itinerary[1]["morning"]["spot"] == ""
        # Day 3: 天安门 应被清空
        assert itinerary[2]["morning"]["spot"] == ""
        # 其他景点应保留
        assert itinerary[0]["afternoon"]["spot"] == "故宫"
        assert itinerary[1]["afternoon"]["spot"] == "颐和园"

    def test_same_day_no_duplicate(self):
        """同一天内多次使用同一景点时，第二个及以后的应被清空。"""
        parsed = {
            "dailyItinerary": [
                {
                    "day": 1,
                    "morning": {"spot": "故宫", "duration": "2h"},
                    "afternoon": {"spot": "故宫", "duration": "2h"},  # 重复，应被清空
                    "evening": {"spot": "", "duration": "", "ticket": "", "transportation": "", "description": ""},
                },
            ]
        }

        TripService._validate_and_fix_trip_data(parsed)

        itinerary = parsed["dailyItinerary"]
        assert itinerary[0]["morning"]["spot"] == "故宫"  # 首次保留
        assert itinerary[0]["afternoon"]["spot"] == ""    # 第二次清空

    def test_food_in_attraction_slot(self):
        """餐饮（如全聚德）被填入 morning/afternoon/evening 时应被清空。"""
        parsed = {
            "dailyItinerary": [
                {
                    "day": 1,
                    "morning": {"spot": "天安门", "duration": "2h"},
                    "afternoon": {"spot": "故宫", "duration": "3h"},
                    "evening": {"spot": "全聚德", "duration": "1h"},  # 餐饮进入景点时段，应被清空
                },
            ]
        }

        TripService._validate_and_fix_trip_data(parsed)

        itinerary = parsed["dailyItinerary"]
        assert itinerary[0]["morning"]["spot"] == "天安门"
        assert itinerary[0]["afternoon"]["spot"] == "故宫"
        assert itinerary[0]["evening"]["spot"] == ""  # 全聚德被清空
        assert itinerary[0]["evening"]["description"] == "景点信息待确认"

    def test_accommodation_food_detection(self):
        """accommodation 字段填入餐饮时应被清空。"""
        parsed = {
            "dailyItinerary": [
                {
                    "day": 1,
                    "morning": {"spot": "天安门"},
                    "afternoon": {"spot": "故宫"},
                    "evening": {"spot": ""},
                    "accommodation": {"spot": "全聚德", "duration": "", "ticket": "", "transportation": "", "description": ""},
                },
            ]
        }

        TripService._validate_and_fix_trip_data(parsed)

        itinerary = parsed["dailyItinerary"]
        assert itinerary[0]["accommodation"]["spot"] == ""  # 全聚德被清空
        assert itinerary[0]["accommodation"]["description"] == "住宿信息待确认"

    def test_empty_daily_itinerary(self):
        """空 dailyItinerary 不应抛出异常。"""
        parsed = {"dailyItinerary": []}
        TripService._validate_and_fix_trip_data(parsed)  # 不应抛出异常

    def test_no_false_positive_for_hotels(self):
        """酒店名称不应被误判为餐饮。"""
        parsed = {
            "dailyItinerary": [
                {
                    "day": 1,
                    "morning": {"spot": "北京饭店", "duration": "2h"},
                    "afternoon": {"spot": "全聚德烤鸭店", "duration": "3h"},
                    "evening": {"spot": ""},
                },
            ]
        }

        TripService._validate_and_fix_trip_data(parsed)

        itinerary = parsed["dailyItinerary"]
        # "北京饭店" 应保留（包含"饭店"但也在 _HOTEL_KEYWORDS 中检查，需要更精确的酒店关键词检查）
        # 实际上"北京饭店"包含"饭店"但酒店关键词检查在前，所以它会被识别为酒店并保留
        # "全聚德烤鸭店" 应被清空（包含"烤鸭"）
        assert itinerary[0]["morning"]["spot"] == "北京饭店"
        assert itinerary[0]["afternoon"]["spot"] == ""  # 全聚德被清空


# ---------------------------------------------------------------------------
# Test 2: _extract_spot_items — 从格式化文本提取 POI 名称
# ---------------------------------------------------------------------------

class TestExtractSpotItems:
    """Test suite for ResearchAgent._extract_spot_items."""

    @staticmethod
    def _make_agent():
        return ResearchAgent(llm=MagicMock())

    def test_extract_from_formatted_text(self):
        """能从 format_search_results 格式的文本中正确提取景点名称。"""
        text = """找到 3 个相关景点：

1. 天安门（北京）
   - 评分：4.8 分
   - 介绍：中国的地标性建筑...

2. 故宫（北京）
   - 评分：4.9 分
   - 介绍：明清两代的皇家宫殿...

3. 颐和园（北京）
   - 评分：4.7 分
   - 标签：世界文化遗产, 皇家园林
"""
        agent = self._make_agent()
        items = agent._extract_spot_items(text, "attraction")

        assert len(items) == 3
        assert items[0].name == "天安门"
        assert items[1].name == "故宫"
        assert items[2].name == "颐和园"
        assert all(item.category == "attraction" for item in items)

    def test_extract_empty_text(self):
        """空文本应返回空列表。"""
        agent = self._make_agent()
        items = agent._extract_spot_items("", "attraction")
        assert items == []

    def test_extract_with_max_limit(self):
        """应限制提取的最大数量。"""
        lines = "\n".join(f"{i}. 景点{i}（北京）" for i in range(1, 21))
        agent = self._make_agent()
        items = agent._extract_spot_items(lines, "attraction", max_items=5)

        assert len(items) == 5
        assert items[0].name == "景点1"
        assert items[4].name == "景点5"

    def test_extract_food_category(self):
        """美食分类应正确标注。"""
        text = "1. 全聚德（北京）\n   - 评分：4.5 分\n"
        agent = self._make_agent()
        items = agent._extract_spot_items(text, "food")

        assert len(items) == 1
        assert items[0].name == "全聚德"
        assert items[0].category == "food"


# ---------------------------------------------------------------------------
# Test 3: review — 候选池合规检查
# ---------------------------------------------------------------------------

class TestReviewPoolCompliance:
    """Test suite for review() pool compliance check."""

    @pytest.mark.asyncio
    async def test_pool_compliance_pass(self):
        """行程仅使用候选池中的景点时应通过。"""
        parsed = {
            "dailyItinerary": [
                {"day": 1, "morning": {"spot": "天安门"}, "afternoon": {"spot": "故宫"}, "evening": {"spot": "景山"}},
                {"day": 2, "morning": {"spot": "颐和园"}, "afternoon": {"spot": "圆明园"}, "evening": {"spot": ""}},
            ]
        }

        bundle = ResearchBundle(
            attractions="...",
            food="...",
            attraction_items=[
                SpotItem(name="天安门", category="attraction"),
                SpotItem(name="故宫", category="attraction"),
                SpotItem(name="景山", category="attraction"),
                SpotItem(name="颐和园", category="attraction"),
                SpotItem(name="圆明园", category="attraction"),
            ],
            food_items=[],
        )

        parsed_plan, result = await review(
            raw_output='{"dailyItinerary": [], "budgetBreakdown": {"accommodation": 0, "food": 0, "transportation": 0, "tickets": 0, "other": 0}}',
            bundle=bundle,
            budget=5000,
            days=2,
        )

        # 替换为实际 parsed 的检查
        parsed_plan, result = await review(
            raw_output='{"city":"北京","days":2,"totalBudget":5000,"dailyItinerary":[{"day":1,"morning":{"spot":"天安门"},"afternoon":{"spot":"故宫"},"evening":{"spot":"景山"}},{"day":2,"morning":{"spot":"颐和园"},"afternoon":{"spot":"圆明园"},"evening":{"spot":""}}],"budgetBreakdown":{"accommodation":1500,"food":1000,"transportation":800,"tickets":500,"other":1200},"tips":[],"warnings":[]}',
            bundle=bundle,
            budget=5000,
            days=2,
        )

        assert result.passed is True
        assert result.code_checks.get("pool_compliance") is True

    @pytest.mark.asyncio
    async def test_pool_compliance_fail(self):
        """行程包含候选池外的景点时应不通过。"""
        parsed = {
            "dailyItinerary": [
                {"day": 1, "morning": {"spot": "天安门"}, "afternoon": {"spot": "故宫"}, "evening": {"spot": ""}},
                {"day": 2, "morning": {"spot": "长城"}, "afternoon": {"spot": "圆明园"}, "evening": {"spot": ""}},  # 长城不在候选池
            ]
        }

        bundle = ResearchBundle(
            attractions="...",
            food="...",
            attraction_items=[
                SpotItem(name="天安门", category="attraction"),
                SpotItem(name="故宫", category="attraction"),
                SpotItem(name="圆明园", category="attraction"),
            ],
            food_items=[],
        )

        raw_json = '{"city":"北京","days":2,"totalBudget":5000,"dailyItinerary":[{"day":1,"morning":{"spot":"天安门"},"afternoon":{"spot":"故宫"},"evening":{"spot":""}},{"day":2,"morning":{"spot":"长城"},"afternoon":{"spot":"圆明园"},"evening":{"spot":""}}],"budgetBreakdown":{"accommodation":1500,"food":1000,"transportation":800,"tickets":500,"other":1200},"tips":[],"warnings":[]}'

        parsed_plan, result = await review(
            raw_output=raw_json,
            bundle=bundle,
            budget=5000,
            days=2,
        )

        assert result.passed is False
        assert result.code_checks.get("pool_compliance") is False
        assert "长城" in result.feedback or "长城" in result.issues[0]

    @pytest.mark.asyncio
    async def test_pool_compliance_no_bundle(self):
        """无候选池时应跳过检查。"""
        raw_json = '{"city":"北京","days":2,"totalBudget":5000,"dailyItinerary":[{"day":1,"morning":{"spot":"天安门"},"afternoon":{"spot":"故宫"},"evening":{"spot":""}},{"day":2,"morning":{"spot":"颐和园"},"afternoon":{"spot":"圆明园"},"evening":{"spot":""}}],"budgetBreakdown":{"accommodation":1500,"food":1000,"transportation":800,"tickets":500,"other":1200},"tips":[],"warnings":[]}'

        parsed_plan, result = await review(
            raw_output=raw_json,
            bundle=None,
            budget=5000,
            days=2,
        )

        assert result.code_checks.get("pool_compliance") == "no_pool"

    @pytest.mark.asyncio
    async def test_pool_compliance_empty_pool(self):
        """候选池为空时应跳过检查。"""
        bundle = ResearchBundle(attractions="", food="", attraction_items=[], food_items=[])

        raw_json = '{"city":"北京","days":2,"totalBudget":5000,"dailyItinerary":[{"day":1,"morning":{"spot":"天安门"},"afternoon":{"spot":"故宫"},"evening":{"spot":""}},{"day":2,"morning":{"spot":"颐和园"},"afternoon":{"spot":"圆明园"},"evening":{"spot":""}}],"budgetBreakdown":{"accommodation":1500,"food":1000,"transportation":800,"tickets":500,"other":1200},"tips":[],"warnings":[]}'

        parsed_plan, result = await review(
            raw_output=raw_json,
            bundle=bundle,
            budget=5000,
            days=2,
        )

        assert result.code_checks.get("pool_compliance") == "no_pool"
