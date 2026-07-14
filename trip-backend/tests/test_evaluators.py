"""
Evaluator 单元测试

对标 Node.js eval/__tests__/evaluators.test.ts（51 个测试）
每个 evaluator 正反两路，覆盖 pass / fail / skip 场景。
"""

from __future__ import annotations

import pytest

# 导入会触发 @register_evaluator 注册
import eval.evaluators  # noqa: F401
from eval.evaluators.general import (
    schema_check,
    poi_city_match,
    keyword_coverage,
    tool_call_audit,
    pace_consistency,
)
from eval.evaluators.domain import (
    pet_constraint_check,
    dietary_constraint_check,
    weather_adaptation_check,
    budget_field_present,
    kid_friendly_check,
)
from eval.evaluators.multi_turn import (
    destination_override,
    context_memory,
    no_forced_itinerary,
)
from eval.types import AgentOutput, Fixture, FixtureExpected, FixtureInput, ToolCall


# ============================================================
# Helpers
# ============================================================

def _out(**kw) -> AgentOutput:
    return AgentOutput(**kw)


def _fix(
    *,
    message: str = "test",
    history: list[dict] | None = None,
    **exp_kw,
) -> Fixture:
    return Fixture(
        id="test-fixture",
        description="test",
        tags=[],
        input=FixtureInput(message=message, history=history or []),
        expected=FixtureExpected(**exp_kw),
        evaluators=[],
    )


# ============================================================
# schema_check (~5)
# ============================================================

class TestSchemaCheck:
    VALID_JSON = {
        "city": "成都",
        "days": 1,
        "totalBudget": 1000,
        "dailyItinerary": [
            {"day": 1, "morning": {"spot": "宽窄巷子"}, "afternoon": {"spot": "锦里"}, "evening": {"spot": "火锅"}},
        ],
        "budgetBreakdown": {"accommodation": 300, "food": 300, "transportation": 100, "tickets": 200, "other": 100},
    }

    def test_json_valid_false_no_json_skip(self):
        """json_valid=False 且无 JSON → pass（跳过）"""
        r = schema_check(_out(), _fix(json_valid=False))
        assert r.passed is True

    def test_json_valid_true_good_json_pass(self):
        """json_valid=True 且 JSON 完整 → pass"""
        r = schema_check(_out(json=self.VALID_JSON), _fix(json_valid=True))
        assert r.passed is True

    def test_json_valid_true_missing_fields_fail(self):
        """json_valid=True 但 JSON 缺关键字段 → fail + reason 含 missing/缺少"""
        r = schema_check(_out(json={"foo": "bar"}), _fix(json_valid=True))
        assert r.passed is False
        assert "缺" in r.reason or "missing" in r.reason.lower()

    def test_json_valid_false_but_has_json_fail(self):
        """json_valid=False 但有 JSON → fail"""
        r = schema_check(_out(json=self.VALID_JSON), _fix(json_valid=False))
        assert r.passed is False

    def test_no_json_but_day_markers_pass(self):
        """无 JSON 但文本含 Day 1 → pass（回退）"""
        r = schema_check(_out(text="Day 1: 宽窄巷子"), _fix(json_valid=True))
        assert r.passed is True

    def test_no_json_but_chinese_day_marker_pass(self):
        """无 JSON 但文本含 第1天 → pass"""
        r = schema_check(_out(text="第1天 宽窄巷子"), _fix(json_valid=True))
        assert r.passed is True

    def test_no_json_no_markers_fail(self):
        """无 JSON 也无 Day 标记 → fail"""
        r = schema_check(_out(text="随便聊聊"), _fix(json_valid=True))
        assert r.passed is False


# ============================================================
# poi_city_match (~5)
# ============================================================

class TestPoiCityMatch:
    def test_no_required_pois_pass(self):
        """没规定 must_contain_pois → pass"""
        r = poi_city_match(_out(), _fix())
        assert r.passed is True

    def test_name_contains_hit_pass(self):
        """JSON 里 name_contains 命中 → pass"""
        out = _out(json={"city": "成都", "dailyItinerary": [{"day": 1, "morning": {"spot": "宽窄巷子景区"}}]})
        f = _fix(must_contain_pois=[{"name_contains": "宽窄巷子", "city": "成都"}])
        r = poi_city_match(out, f)
        assert r.passed is True

    def test_poi_city_mismatch_fail(self):
        """POI 城市不符（上海 vs 成都）→ fail"""
        out = _out(json={
            "city": "上海",
            "dailyItinerary": [{"day": 1, "morning": {"spot": "外滩", "city": "上海"}}],
        })
        f = _fix(must_contain_pois=[{"name_contains": "外滩", "city": "成都"}])
        r = poi_city_match(out, f)
        assert r.passed is False
        assert "城市不符" in r.reason

    def test_poi_in_nearby_city_pass(self):
        """POI 落在周边城市（都江堰对成都 ~50km）→ pass"""
        out = _out(json={
            "city": "都江堰",
            "dailyItinerary": [{"day": 1, "morning": {"spot": "都江堰景区", "city": "都江堰"}}],
        })
        f = _fix(must_contain_pois=[{"name_contains": "都江堰", "city": "成都"}])
        r = poi_city_match(out, f)
        assert r.passed is True

    def test_poi_not_found_fail(self):
        """POI 完全没出现 → fail"""
        out = _out(json={"city": "杭州", "dailyItinerary": [{"day": 1, "morning": {"spot": "西湖"}}]})
        f = _fix(must_contain_pois=[{"name_contains": "兵马俑"}])
        r = poi_city_match(out, f)
        assert r.passed is False

    def test_poi_missing_city_field_pass(self):
        """JSON 里 POI 缺 city 字段 → pass（无法校验）"""
        out = _out(json={"city": "上海", "dailyItinerary": [{"day": 1, "morning": {"spot": "外滩"}}]})
        f = _fix(must_contain_pois=[{"name_contains": "外滩", "city": "上海"}])
        r = poi_city_match(out, f)
        assert r.passed is True


# ============================================================
# keyword_coverage (~5)
# ============================================================

class TestKeywordCoverage:
    def test_all_keywords_hit_pass(self):
        """必含关键词都命中 → pass"""
        out = _out(text="推荐宽窄巷子和锦里，美食必吃火锅")
        f = _fix(must_contain_keywords=["宽窄巷子", "火锅"])
        assert keyword_coverage(out, f).passed is True

    def test_missing_keyword_fail(self):
        """缺必含关键词 → fail + reason 含缺失词"""
        out = _out(text="推荐宽窄巷子")
        f = _fix(must_contain_keywords=["宽窄巷子", "火锅"])
        r = keyword_coverage(out, f)
        assert r.passed is False
        assert "火锅" in r.reason

    def test_forbidden_keyword_fail(self):
        """出现禁用关键词 → fail"""
        out = _out(text="推荐蹦极 + 火锅")
        f = _fix(must_not_contain_keywords=["蹦极"])
        r = keyword_coverage(out, f)
        assert r.passed is False
        assert "蹦极" in r.reason

    def test_no_rules_pass(self):
        """无关键词规则 → pass"""
        assert keyword_coverage(_out(), _fix()).passed is True

    def test_any_mode_one_hit_pass(self):
        """any 模式命中一个即可 → pass"""
        out = _out(text="推荐火锅")
        f = _fix(must_contain_keywords=["火锅", "串串"])
        f.expected.keyword_match_mode = "any"
        # keyword_coverage 读 getattr(fixture.expected, "keyword_match_mode", "all")
        # FixtureExpected 没有 keyword_match_mode 字段，但 Python dataclass 允许 setattr
        assert keyword_coverage(out, f).passed is True

    def test_any_mode_none_hit_fail(self):
        """any 模式全未命中 → fail"""
        out = _out(text="推荐米饭")
        f = _fix(must_contain_keywords=["火锅", "串串"])
        f.expected.keyword_match_mode = "any"
        r = keyword_coverage(out, f)
        assert r.passed is False


# ============================================================
# tool_call_audit (~4)
# ============================================================

class TestToolCallAudit:
    def test_no_rules_pass(self):
        """无 tool_calls 规则 → pass"""
        assert tool_call_audit(_out(), _fix()).passed is True

    def test_min_calls_not_met_fail(self):
        """min_calls 1 但调用 0 次 → fail"""
        out = _out(tool_calls=[])
        f = _fix(tool_calls=[{"name": "retrieve_knowledge", "min_calls": 1}])
        assert tool_call_audit(out, f).passed is False

    def test_min_calls_met_pass(self):
        """min_calls 1 调用 2 次 → pass"""
        out = _out(tool_calls=[ToolCall(name="retrieve_knowledge"), ToolCall(name="retrieve_knowledge")])
        f = _fix(tool_calls=[{"name": "retrieve_knowledge", "min_calls": 1}])
        assert tool_call_audit(out, f).passed is True

    def test_max_calls_exceeded_fail(self):
        """max_calls 0 但调用 1 次 → fail"""
        out = _out(tool_calls=[ToolCall(name="getWeather")])
        f = _fix(tool_calls=[{"name": "getWeather", "max_calls": 0}])
        assert tool_call_audit(out, f).passed is False

    def test_camel_snake_normalization_pass(self):
        """驼峰/蛇形归一化：get_weather == getWeather → pass"""
        out = _out(tool_calls=[ToolCall(name="get_weather")])
        f = _fix(tool_calls=[{"name": "getWeather", "min_calls": 1}])
        assert tool_call_audit(out, f).passed is True


# ============================================================
# pace_consistency (~4)
# ============================================================

class TestPaceConsistency:
    def test_days_match_pass(self):
        """days 匹配 → pass"""
        out = _out(json={"days": 2, "dailyItinerary": [{"day": 1, "morning": {"spot": "A"}}, {"day": 2, "morning": {"spot": "B"}}]})
        f = _fix(days=2)
        assert pace_consistency(out, f).passed is True

    def test_days_mismatch_fail(self):
        """days 不符 → fail"""
        out = _out(json={"days": 2, "dailyItinerary": [{"day": 1}, {"day": 2}]})
        f = _fix(days=3)
        assert pace_consistency(out, f).passed is False

    def test_too_many_activities_per_day_fail(self):
        """每天活动数超上限 → fail"""
        out = _out(json={
            "days": 1,
            "dailyItinerary": [{"day": 1, "morning": {"spot": "A"}, "afternoon": {"spot": "B"}, "evening": {"spot": "C"}}],
        })
        f = _fix(days=1, max_activities_per_day=2)
        assert pace_consistency(out, f).passed is False

    def test_no_days_info_fail(self):
        """无 JSON 也无 Day 文本 → fail"""
        out = _out(text="随便聊聊")
        f = _fix(days=3)
        assert pace_consistency(out, f).passed is False

    def test_text_day_markers_count_pass(self):
        """文本中 Day 标记数匹配 → pass"""
        out = _out(text="Day 1 玩 Day 2 玩 Day 3 玩")
        f = _fix(days=3)
        assert pace_consistency(out, f).passed is True


# ============================================================
# pet_constraint_check (~4)
# ============================================================

class TestPetConstraintCheck:
    def test_no_pet_mention_skip(self):
        """用户没提宠物 → pass（跳过）"""
        f = _fix(message="成都 3 天")
        assert pet_constraint_check(_out(), f).passed is True

    def test_pet_tip_present_no_banned_pass(self):
        """用户带金毛 + Agent 提到牵引绳 + 无禁入场所 → pass"""
        f = _fix(message="我带金毛去上海 2 天")
        out = _out(text="推荐外滩遛狗，请牵好牵引绳，注意防疫。")
        assert pet_constraint_check(out, f).passed is True

    def test_banned_venue_zoo_fail(self):
        """用户带金毛 + Agent 推荐动物园 → fail + reason 含动物园"""
        f = _fix(message="我带金毛去上海 2 天")
        out = _out(text="推荐上海动物园，请牵好牵引绳。")
        r = pet_constraint_check(out, f)
        assert r.passed is False
        assert "动物园" in r.reason

    def test_banned_venue_in_json_fail(self):
        """JSON 里推荐了美术馆 → fail"""
        f = _fix(message="我带金毛去上海 2 天")
        out = _out(
            text="请牵好牵引绳",
            json={"city": "上海", "dailyItinerary": [{"day": 1, "morning": {"spot": "上海美术馆"}}]},
        )
        r = pet_constraint_check(out, f)
        assert r.passed is False
        assert "美术馆" in r.reason

    def test_banned_venue_with_warning_still_fail(self):
        """有禁入场所但有宠物警告 → 仍然 fail"""
        f = _fix(message="我带柯基去成都")
        out = _out(text="注意：虽然可以带宠物，但推荐成都动物园，请牵好牵引绳。")
        r = pet_constraint_check(out, f)
        assert r.passed is False


# ============================================================
# dietary_constraint_check (~6)
# ============================================================

class TestDietaryConstraintCheck:
    def test_no_dietary_mention_skip(self):
        """用户没提饮食禁忌 → pass"""
        f = _fix(message="成都 3 天")
        assert dietary_constraint_check(_out(), f).passed is True

    def test_halal_good_pass(self):
        """用户说清真 + Agent 推荐清真餐厅 + 无禁忌 → pass"""
        f = _fix(message="我是穆斯林，3 天北京")
        out = _out(text="推荐牛街清真餐厅，鸿宾楼等都是清真美食。")
        assert dietary_constraint_check(out, f).passed is True

    def test_halal_banned_food_fail(self):
        """用户说清真 + Agent 推荐烤鸭/涮羊肉 → fail"""
        f = _fix(message="我是穆斯林，3 天北京")
        out = _out(text="推荐烤鸭、涮羊肉、清真小吃")
        r = dietary_constraint_check(out, f)
        assert r.passed is False

    def test_halal_avoidance_context_pass(self):
        """'无猪肉''避免猪肉' → pass（避免语境）"""
        f = _fix(message="我是穆斯林，3 天北京")
        out = _out(text="行程承诺全程无猪肉、避免猪肉相关推荐，只去清真餐厅。")
        assert dietary_constraint_check(out, f).passed is True

    def test_halal_quanjude_excluded_pass(self):
        """'全聚德已排除' → pass（避免语境）"""
        f = _fix(message="我是穆斯林，3 天北京")
        out = _out(text="推荐牛街清真餐厅。⚠️ 注意：四季民福、全聚德等烤鸭店未标注清真，我已帮你排除。")
        assert dietary_constraint_check(out, f).passed is True

    def test_vegetarian_good_pass(self):
        """全素食行程 → pass"""
        f = _fix(message="我吃素，杭州 2 天")
        out = _out(text="推荐素食餐厅，素菜馆和斋饭都不错。")
        assert dietary_constraint_check(out, f).passed is True

    def test_halal_missing_required_fail(self):
        """缺少饮食提示（没提清真）→ fail"""
        f = _fix(message="我是穆斯林，3 天北京")
        out = _out(text="推荐北京烤鸭，很好吃。")
        r = dietary_constraint_check(out, f)
        assert r.passed is False


# ============================================================
# weather_adaptation_check (~4)
# ============================================================

class TestWeatherAdaptationCheck:
    def test_no_weather_mention_skip(self):
        """用户没提天气 → pass"""
        f = _fix(message="杭州 2 天")
        assert weather_adaptation_check(_out(), f).passed is True

    def test_rain_indoor_getweather_pass(self):
        """用户说下雨 + Agent 提到室内 + 调 getWeather → pass"""
        f = _fix(message="下周去杭州 2 天一直下雨")
        out = _out(
            text="雨天推荐室内博物馆、灵隐寺。备选方案已准备好。",
            tool_calls=[ToolCall(name="getWeather")],
        )
        assert weather_adaptation_check(out, f).passed is True

    def test_rain_outdoor_activity_fail(self):
        """用户说下雨 + Agent 推荐露天草坪 → fail"""
        f = _fix(message="下周去杭州 2 天一直下雨")
        out = _out(
            text="推荐户外活动，草坪野餐适合雨天。",
            tool_calls=[ToolCall(name="getWeather")],
        )
        r = weather_adaptation_check(out, f)
        assert r.passed is False
        assert "草坪" in r.reason

    def test_rain_no_getweather_fail(self):
        """用户说下雨但 Agent 没调 getWeather → fail"""
        f = _fix(message="下周去杭州 2 天一直下雨")
        out = _out(text="雨天推荐室内活动，备选方案已准备。")
        r = weather_adaptation_check(out, f)
        assert r.passed is False
        assert "getWeather" in r.reason


# ============================================================
# budget_field_present (~3)
# ============================================================

class TestBudgetFieldPresent:
    def test_no_price_requirement_skip(self):
        """没要求 price → pass"""
        assert budget_field_present(_out(), _fix()).passed is True

    def test_all_slots_have_ticket_pass(self):
        """每个 slot 都有 ticket 含价格 → pass"""
        out = _out(json={
            "dailyItinerary": [
                {"day": 1, "morning": {"spot": "A", "ticket": "￥50"}, "afternoon": {"spot": "B", "ticket": "￥30"}},
            ],
        })
        f = _fix(activities_have_price_field=True)
        assert budget_field_present(out, f).passed is True

    def test_slot_missing_ticket_fail(self):
        """有 slot 缺 ticket → fail"""
        out = _out(json={
            "dailyItinerary": [
                {"day": 1, "morning": {"spot": "A", "ticket": "￥50"}, "afternoon": {"spot": "B"}},
            ],
        })
        f = _fix(activities_have_price_field=True)
        r = budget_field_present(out, f)
        assert r.passed is False
        assert "B" in r.reason

    def test_no_json_fail(self):
        """无 JSON → fail"""
        f = _fix(activities_have_price_field=True)
        r = budget_field_present(_out(), f)
        assert r.passed is False


# ============================================================
# kid_friendly_check (~4)
# ============================================================

class TestKidFriendlyCheck:
    def test_no_kid_mention_skip(self):
        """用户没提孩子 → pass"""
        f = _fix(message="西安 2 天")
        assert kid_friendly_check(_out(), f).passed is True

    def test_kid_tip_present_no_bad_pass(self):
        """用户带 6 岁孩子 + Agent 提到儿童休息 → pass"""
        f = _fix(message="带 6 岁小孩去西安 2 天")
        out = _out(text="行程轻松，儿童需午休。推荐兵马俑。")
        assert kid_friendly_check(out, f).passed is True

    def test_bad_activity_climbing_fail(self):
        """用户带 6 岁孩子 + Agent 推荐登山 → fail"""
        f = _fix(message="带 6 岁小孩去西安 2 天")
        out = _out(text="推荐登山、华山徒步。儿童需午休。")
        r = kid_friendly_check(out, f)
        assert r.passed is False
        assert "登山" in r.reason

    def test_bad_activity_bungee_fail(self):
        """含蹦极 → fail"""
        f = _fix(message="带 5 岁孩子去三亚")
        out = _out(text="推荐蹦极、潜水体验。儿童注意安全。")
        r = kid_friendly_check(out, f)
        assert r.passed is False

    def test_normal_family_trip_pass(self):
        """普通亲子行程 → pass"""
        f = _fix(message="带宝宝去成都 2 天")
        out = _out(text="推荐大熊猫基地，孩子会很喜欢。亲子活动丰富，注意休息。")
        assert kid_friendly_check(out, f).passed is True

    def test_bad_activity_in_json_fail(self):
        """JSON 行程含攀岩 POI → fail"""
        f = _fix(message="带小孩去桂林")
        out = _out(
            text="亲子行程，儿童注意安全。",
            json={"city": "桂林", "dailyItinerary": [{"day": 1, "morning": {"spot": "攀岩基地"}}]},
        )
        r = kid_friendly_check(out, f)
        assert r.passed is False
        assert "攀岩" in r.reason


# ============================================================
# destination_override (~3)
# ============================================================

class TestDestinationOverride:
    def test_no_history_skip(self):
        """无 history → pass"""
        f = _fix(message="改成重庆")
        assert destination_override(_out(), f).passed is True

    def test_new_destination_followed_pass(self):
        """多轮改目的地 + Agent 跟随 → pass"""
        f = _fix(
            message="那改成重庆吧",
            history=[
                {"role": "user", "content": "成都 3 天"},
                {"role": "assistant", "content": "好的，成都..."},
            ],
            must_contain_pois=[{"name_contains": "解放碑", "city": "重庆"}],
            must_not_contain_keywords=["宽窄巷子", "锦里", "春熙路"],
        )
        out = _out(
            text="推荐重庆解放碑、洪崖洞。",
            json={"city": "重庆", "dailyItinerary": [{"day": 1, "morning": {"spot": "解放碑步行街"}}]},
        )
        assert destination_override(out, f).passed is True

    def test_old_destination_still_present_fail(self):
        """多轮改目的地 + Agent 没跟随 → fail + reason 含原目的地"""
        f = _fix(
            message="那改成重庆吧",
            history=[
                {"role": "user", "content": "成都 3 天"},
                {"role": "assistant", "content": "好的，成都..."},
            ],
            must_contain_pois=[{"name_contains": "解放碑", "city": "重庆"}],
            must_not_contain_keywords=["宽窄巷子", "锦里", "春熙路"],
        )
        out = _out(
            text="成都宽窄巷子、锦里必去",
            json={"city": "成都", "dailyItinerary": [{"day": 1, "morning": {"spot": "宽窄巷子"}}]},
        )
        r = destination_override(out, f)
        assert r.passed is False
        assert "宽窄巷子" in r.reason


# ============================================================
# context_memory (~3)
# ============================================================

class TestContextMemory:
    def test_no_history_skip(self):
        """无 history → pass"""
        assert context_memory(_out(), _fix()).passed is True

    def test_context_keywords_present_pass(self):
        """多轮追问 + Agent 提到上文 POI → pass"""
        f = _fix(
            message="Day 2 西湖游船多少钱？",
            history=[
                {"role": "user", "content": "杭州 2 天"},
                {"role": "assistant", "content": "Day 1: ..., Day 2: 西湖游船。"},
            ],
            must_contain_keywords=["西湖", "游船", "码头"],
        )
        out = _out(text="西湖游船在花港码头，120元/人。")
        assert context_memory(out, f).passed is True

    def test_context_keywords_missing_fail(self):
        """多轮追问 + Agent 答非所问 → fail"""
        f = _fix(
            message="Day 2 西湖游船多少钱？",
            history=[
                {"role": "user", "content": "杭州 2 天"},
                {"role": "assistant", "content": "Day 2: 西湖游船。"},
            ],
            must_contain_keywords=["西湖", "游船", "码头"],
        )
        out = _out(text="好的，给你推荐成都 3 天行程...")
        r = context_memory(out, f)
        assert r.passed is False

    def test_empty_must_contain_pass(self):
        """空 must_contain → pass"""
        f = _fix(
            message="追问",
            history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
            must_contain_keywords=[],
        )
        assert context_memory(_out(text="随便"), f).passed is True


# ============================================================
# no_forced_itinerary (~4)
# ============================================================

class TestNoForcedItinerary:
    def test_non_rejection_fixture_skip(self):
        """非反例 fixture → pass"""
        f = _fix(days=3)
        assert no_forced_itinerary(_out(), f).passed is True

    def test_rejection_polite_no_itinerary_pass(self):
        """反例 + Agent 礼貌拒绝（不输出行程）→ pass"""
        f = _fix(json_valid=False, is_recommendation=True)
        out = _out(text="推荐这几个 6 月适合去的城市：青岛、桂林、丽江。")
        assert no_forced_itinerary(out, f).passed is True

    def test_rejection_with_day1_text_fail(self):
        """反例 + Agent 硬塞 Day 1 行程 → fail"""
        f = _fix(json_valid=False, is_recommendation=True)
        out = _out(text="推荐成都 Day 1：上午宽窄巷子，下午锦里。")
        r = no_forced_itinerary(out, f)
        assert r.passed is False

    def test_rejection_with_json_itinerary_fail(self):
        """反例 + Agent 输出 JSON dailyItinerary → fail"""
        f = _fix(json_valid=False, is_recommendation=True)
        out = _out(
            text="推荐如下",
            json={"dailyItinerary": [{"day": 1, "morning": {"spot": "A"}}]},
        )
        r = no_forced_itinerary(out, f)
        assert r.passed is False

    def test_rejection_chinese_day_marker_fail(self):
        """反例 + 文本含 第1天 → fail"""
        f = _fix(json_valid=False, is_recommendation=True)
        out = _out(text="第1天 推荐去宽窄巷子")
        r = no_forced_itinerary(out, f)
        assert r.passed is False
