"""Tests for intent completion (T1)."""

import pytest
from src.services.agent.intent import (
    check_completeness,
    _build_clarify_field,
    _extract_city,
    ClarifyField,
)


class TestExtractCity:
    """_extract_city() 城市提取测试。"""

    def test_single_city(self):
        assert _extract_city("我想去成都玩") == "成都"

    def test_departure_to_destination_picks_last(self):
        """'从北京到上海' → 取句末目的地'上海'"""
        assert _extract_city("从北京到上海") == "上海"

    def test_short_city_in_compound_name(self):
        """短城市名不应误匹配更长地名中的片段，取最后出现的城市"""
        assert _extract_city("去北海公园转转") == "北海"

    def test_no_city(self):
        assert _extract_city("你好") is None


class TestCheckCompleteness:
    """check_completeness() 测试。"""

    def test_missing_city(self):
        missing, clarified = check_completeness({"days": 2, "budget": 3000})
        assert "city" in missing
        assert "days" not in missing
        assert "budget" not in missing
        assert clarified == {}

    def test_missing_days(self):
        missing, clarified = check_completeness({"city": "北京", "budget": 3000})
        assert "days" in missing
        assert "city" not in missing
        assert "budget" not in missing

    def test_missing_budget(self):
        missing, clarified = check_completeness({"city": "北京", "days": 2})
        assert "budget" in missing
        assert "city" not in missing
        assert "days" not in missing

    def test_all_complete(self):
        missing, clarified = check_completeness({"city": "北京", "days": 2, "budget": 3000})
        assert missing == []
        assert clarified == {}

    def test_history_city_inherit(self):
        """历史对话有城市时，city 从历史继承，不列为 missing。"""
        history = [
            {"role": "user", "content": "我想去北京玩"},
            {"role": "ai", "content": "好的，北京是个好选择"},
        ]
        missing, clarified = check_completeness({"days": 2, "budget": 3000}, history)
        assert "city" not in missing
        assert clarified.get("city") == "北京"

    def test_city_empty_string(self):
        missing, _ = check_completeness({"city": "", "days": 2, "budget": 3000})
        assert "city" in missing

    def test_days_zero(self):
        missing, _ = check_completeness({"city": "北京", "days": 0, "budget": 3000})
        assert "days" in missing

    def test_budget_zero(self):
        missing, _ = check_completeness({"city": "北京", "days": 2, "budget": 0})
        assert "budget" in missing

    def test_departure_city_optional(self):
        """出发城市为可选字段，不影响完整性。"""
        missing, _ = check_completeness({"city": "北京", "days": 2, "budget": 3000})
        assert "departure_city" not in missing


class TestBuildClarifyField:
    """_build_clarify_field() 测试。"""

    def test_city_field(self):
        f = _build_clarify_field("city")
        assert f.key == "city"
        assert f.label == "目的地"
        assert f.field_type == "select"
        assert len(f.options) > 0
        assert "北京" in f.options

    def test_days_field(self):
        f = _build_clarify_field("days")
        assert f.key == "days"
        assert f.label == "天数"
        assert f.field_type == "select"
        assert "1天" in f.options
        assert "7天" in f.options

    def test_budget_field(self):
        f = _build_clarify_field("budget")
        assert f.key == "budget"
        assert f.label == "预算（元）"
        assert f.field_type == "select"
        assert "1000-3000" in f.options

    def test_departure_city_field(self):
        f = _build_clarify_field("departure_city")
        assert f.key == "departure_city"
        assert f.required is False
        assert f.field_type == "text"

    def test_unknown_key(self):
        f = _build_clarify_field("unknown")
        assert f.key == "unknown"
        assert f.field_type == "text"
