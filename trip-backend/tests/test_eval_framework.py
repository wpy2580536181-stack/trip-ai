"""
Eval 框架自身测试

- geo.py: haversine_distance, is_city_or_nearby
- runner.py: load_fixtures, summarize, run_fixture (mock)
- registry.py: list_evaluators, get_evaluator
- mock_agent.py: 行程 / rejection / 默认
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

# 触发注册
import eval.evaluators  # noqa: F401
from eval.geo import haversine_distance, is_city_or_nearby, city_distance_km
from eval.registry import list_evaluators, get_evaluator
from eval.runner import load_fixtures, summarize, run_fixture
from eval.mock_agent import mock_agent
from eval.types import AgentOutput, Fixture, FixtureExpected, FixtureInput, FixtureResult, EvalResult, ToolCall


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "trip-planning"


# ============================================================
# geo.py (~4)
# ============================================================

class TestGeo:
    def test_haversine_known_pair(self):
        """上海-苏州约 85km"""
        d = city_distance_km("上海", "苏州")
        assert d is not None
        assert 80 < d < 90

    def test_is_city_or_nearby_same_city(self):
        """同名 → True"""
        assert is_city_or_nearby("成都", "成都") is True

    def test_is_city_or_nearby_dujiangyan_chengdu(self):
        """都江堰 ~50km → True"""
        assert is_city_or_nearby("都江堰", "成都") is True

    def test_is_city_or_nearby_emeishan_chengdu(self):
        """峨眉山 ~140km → False"""
        assert is_city_or_nearby("峨眉山", "成都") is False

    def test_is_city_or_nearby_unknown_city(self):
        """未登记城市 → False"""
        assert is_city_or_nearby("火星城", "成都") is False

    def test_haversine_beijing_shanghai(self):
        """北京-上海约 1068km"""
        d = city_distance_km("北京", "上海")
        assert d is not None
        assert 1000 < d < 1200


# ============================================================
# registry.py (~3)
# ============================================================

class TestRegistry:
    def test_list_evaluators_count(self):
        """应有 16 个 evaluator（相对初版 13 新增了 multi_turn 与 ragas 系列）"""
        names = list_evaluators()
        assert len(names) == 16

    def test_get_evaluator_exists(self):
        """schema_check 应存在"""
        fn = get_evaluator("schema_check")
        assert fn is not None
        assert callable(fn)

    def test_get_evaluator_not_exists(self):
        """不存在的 evaluator → None"""
        assert get_evaluator("nonexistent_evaluator_xyz") is None


# ============================================================
# runner.py (~4)
# ============================================================

class TestRunner:
    def test_load_fixtures_count(self):
        """加载 fixture 数量 = 10"""
        fixtures = load_fixtures(FIXTURES_DIR)
        assert len(fixtures) == 10

    def test_load_fixtures_have_required_fields(self):
        """每个 fixture 都有 id / input / expected"""
        fixtures = load_fixtures(FIXTURES_DIR)
        for f in fixtures:
            assert f.id
            assert f.input.message

    def test_summarize_statistics(self):
        """summarize 统计正确"""
        results = [
            FixtureResult(
                fixture_id="f1", description="d1", tags=["trip"],
                passed=True, evaluator_results={"schema_check": EvalResult(passed=True)},
                duration_ms=100,
            ),
            FixtureResult(
                fixture_id="f2", description="d2", tags=["trip"],
                passed=False, evaluator_results={"schema_check": EvalResult(passed=False, reason="bad")},
                duration_ms=200,
            ),
        ]
        summary = summarize(results)
        assert summary.total_fixtures == 2
        assert summary.passed_fixtures == 1
        assert summary.failed_fixtures == 1
        assert summary.pass_rate == pytest.approx(0.5)
        assert summary.by_tag["trip"].total == 2
        assert summary.by_tag["trip"].passed == 1
        assert summary.by_evaluator["schema_check"].total == 2

    def test_run_fixture_with_mock_agent(self):
        """run_fixture 使用 mock agent"""
        fixture = Fixture(
            id="test-run",
            description="test run_fixture",
            tags=[],
            input=FixtureInput(message="成都 3 天"),
            expected=FixtureExpected(days=3, json_valid=True),
            evaluators=["schema_check"],
        )
        result = asyncio.get_event_loop().run_until_complete(
            run_fixture(fixture, mock_agent=mock_agent)
        )
        assert result.fixture_id == "test-run"
        assert "schema_check" in result.evaluator_results

    def test_multi_sample_voting(self):
        """多采样投票：2/3 pass → pass"""
        call_count = 0

        def flaky_agent(fixture: Fixture) -> AgentOutput:
            nonlocal call_count
            call_count += 1
            # 前两次 pass（有 JSON），第三次 fail（无 JSON）
            if call_count <= 2:
                return AgentOutput(
                    json={
                        "city": "成都", "days": 3, "totalBudget": 1000,
                        "dailyItinerary": [{"day": 1}],
                        "budgetBreakdown": {},
                    }
                )
            return AgentOutput(text="没有 JSON")

        fixture = Fixture(
            id="test-vote",
            description="vote test",
            tags=[],
            input=FixtureInput(message="成都 3 天"),
            expected=FixtureExpected(json_valid=True),
            evaluators=["schema_check"],
        )
        result = asyncio.get_event_loop().run_until_complete(
            run_fixture(fixture, mock_agent=flaky_agent, samples=3)
        )
        assert result.evaluator_results["schema_check"].passed is True
        assert result.evaluator_results["schema_check"].details["pass_count"] == 2


# ============================================================
# mock_agent.py (~3)
# ============================================================

class TestMockAgent:
    def test_trip_tags_return_json(self):
        """行程 tags → 返回 JSON + text"""
        fixture = Fixture(
            id="mock-trip",
            description="trip",
            tags=["trip"],
            input=FixtureInput(message="成都 3 天"),
            expected=FixtureExpected(days=3, must_contain_pois=[{"name": "宽窄巷子"}]),
            evaluators=[],
        )
        out = mock_agent(fixture)
        assert out.json is not None
        assert out.json["days"] == 3
        assert out.json["city"] == "成都"
        assert "成都" in out.text

    def test_rejection_tags_return_text(self):
        """rejection tags → 返回简短文本"""
        fixture = Fixture(
            id="mock-reject",
            description="rejection",
            tags=["rejection"],
            input=FixtureInput(message="今天天气怎么样"),
            expected=FixtureExpected(),
            evaluators=[],
        )
        out = mock_agent(fixture)
        assert out.json is None
        assert len(out.text) > 0

    def test_default_response(self):
        """默认 → 返回默认响应"""
        fixture = Fixture(
            id="mock-default",
            description="default",
            tags=[],
            input=FixtureInput(message="hi"),
            expected=FixtureExpected(),
            evaluators=[],
        )
        out = mock_agent(fixture)
        assert "mock" in out.text.lower()
