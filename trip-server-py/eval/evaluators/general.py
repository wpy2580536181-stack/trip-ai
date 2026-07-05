"""
通用 evaluator

- schema_check: 验证 JSON 结构合规
- poi_city_match: 验证 POI 在期望城市（含 100km 周边）
- keyword_coverage: 验证必含/必不含关键词
- tool_call_audit: 验证工具调用次数合规
- pace_consistency: 验证每天活动数不超限
"""

from __future__ import annotations

import re
import json
from typing import Any

from eval.registry import register_evaluator
from eval.types import AgentOutput, EvalResult, Fixture
from eval.geo import is_city_or_nearby

# Required fields for a valid TripContentSchema JSON
_SCHEMA_REQUIRED_FIELDS = {"city", "days", "dailyItinerary", "budgetBreakdown", "totalBudget"}


# ============================================================
# Helpers
# ============================================================

def _normalize_tool_name(name: str) -> str:
    """归一化工具名：小写 + 去掉下划线/连字符"""
    return re.sub(r"[_\-]", "", name.lower())


def _extract_poi_names(output: AgentOutput) -> list[str]:
    """从 output 抽取所有 POI 名（JSON 行程 + markdown 文本）"""
    names: list[str] = []

    # 1) JSON dailyItinerary 里的 spot
    if output.json and isinstance(output.json.get("dailyItinerary"), list):
        for day in output.json["dailyItinerary"]:
            for slot_key in ("morning", "afternoon", "evening"):
                slot = day.get(slot_key)
                if slot and slot.get("spot"):
                    names.append(slot["spot"])

    # 2) Markdown 加粗 **XXX**
    bold_re = re.compile(r"\*\*([^*]{2,30})\*\*")
    for m in bold_re.finditer(output.text):
        content = m.group(1).strip()
        if re.match(r"Day\s*\d+", content):
            continue
        if re.match(r"第\s*\d+\s*[天日]", content):
            continue
        if re.match(r"^\d+[.、]", content):
            continue
        if re.search(r"[0-9]+:00|上午|下午|中午|晚上|清晨|傍晚", content) and not re.search(
            r"[一-龥]{4,}", content
        ):
            continue
        names.append(content)

    # 3) 时段前缀 "上午/中午/下午/晚上 XXX"
    slot_re = re.compile(
        r"(?:上午|中午|下午|晚上|清晨|傍晚)\s*[::]?\s*\*?\*?([^*\n]{2,30})"
    )
    for m in slot_re.finditer(output.text):
        content = m.group(1).strip().replace("*", "").strip()
        cleaned = re.split(r"[，。；,;\n]", content)[0].strip()
        if len(cleaned) >= 2:
            names.append(cleaned)

    return list(dict.fromkeys(names))  # deduplicate preserving order


def _find_poi_city(output: AgentOutput, poi_name: str) -> str | None:
    """在 output.json 中查找某个 POI 名对应的 city 字段"""
    if not output.json or not isinstance(output.json.get("dailyItinerary"), list):
        return None
    for day in output.json["dailyItinerary"]:
        for slot_key in ("morning", "afternoon", "evening"):
            slot = day.get(slot_key)
            if slot and slot.get("spot") == poi_name:
                return slot.get("city") or output.json.get("city")
    return None


# ============================================================
# 1. schema_check
# ============================================================

@register_evaluator("schema_check")
def schema_check(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证 JSON 结构合规（或 markdown Day 标记回退）"""
    expected = fixture.expected.json_valid

    # json_valid 未指定（默认 False 且没有显式设置）→ 跳过
    # 用 dataclass 默认值 False 来判定；如果 fixture 没有要求就跳过
    if expected is False and output.json is None:
        return EvalResult(passed=True, reason="json_valid=false 且无 JSON，跳过")

    if expected is False:
        if output.json is None:
            return EvalResult(passed=True)
        return EvalResult(
            passed=False,
            reason=f"expected no JSON (json_valid=false) but got valid JSON: {str(output.json)[:80]}",
        )

    # expected=True
    if output.json is not None:
        json_data: dict[str, Any] = output.json
        missing_fields = _SCHEMA_REQUIRED_FIELDS - set(json_data.keys())
        if not missing_fields:
            days = json_data.get("days", 0)
            itin = json_data.get("dailyItinerary", [])
            itin_days = len(itin) if isinstance(itin, list) else 0
            return EvalResult(passed=True, details={"days": days, "itineraryDays": itin_days})
        return EvalResult(
            passed=False,
            reason=f"JSON 缺少必要字段: {', '.join(sorted(missing_fields))}",
            details={"missing": sorted(missing_fields)},
        )

    # 没有 JSON → 放宽：text 含 "Day N" 或 "第N天" 标记也算 pass
    has_day_markers = re.search(r"Day\s*\d+|第\s*\d+\s*天", output.text, re.IGNORECASE)
    if has_day_markers:
        return EvalResult(passed=True, reason="无 JSON 但文本含 Day 标记，按结构化输出处理")
    return EvalResult(passed=False, reason="expected valid JSON or markdown Day markers but got neither")


# ============================================================
# 2. poi_city_match
# ============================================================

@register_evaluator("poi_city_match")
def poi_city_match(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证 must_contain_pois 中的每个 POI 都在 output 中出现且城市匹配"""
    required = fixture.expected.must_contain_pois
    if not required:
        return EvalResult(passed=True, reason="no must_contain_pois, skipping")

    poi_names = _extract_poi_names(output)

    missing: list[str] = []
    city_mismatch: list[dict[str, Any]] = []

    for req in required:
        req_name = req.get("name")
        req_name_contains = req.get("name_contains")
        needle = req_name or req_name_contains
        if not needle:
            continue

        found = None
        for n in poi_names:
            if req_name and n == req_name:
                found = n
                break
            if req_name_contains and req_name_contains in n:
                found = n
                break

        if not found:
            missing.append(needle)
            continue

        # 城市校验
        req_city = req.get("city")
        if req_city:
            found_city = _find_poi_city(output, found)
            if found_city and not is_city_or_nearby(found_city, req_city):
                city_mismatch.append({"poi": req, "found": found_city})

    if not missing and not city_mismatch:
        return EvalResult(passed=True, details={"checkedPois": len(required)})

    reasons: list[str] = []
    if missing:
        reasons.append(f"未找到 POI: {', '.join(missing)}")
    if city_mismatch:
        parts = []
        for cm in city_mismatch:
            poi = cm["poi"]
            poi_label = poi.get("name") or poi.get("name_contains", "?")
            parts.append(f"{poi_label} 期望 {poi.get('city')} 实际 {cm['found']}")
        reasons.append(f"城市不符: {'; '.join(parts)}")
    return EvalResult(passed=False, reason="; ".join(reasons))


# ============================================================
# 3. keyword_coverage
# ============================================================

@register_evaluator("keyword_coverage")
def keyword_coverage(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证必含/必不含关键词（支持 all/any 模式）
    
    对 must_not 关键词，会做上下文感知检查：
    - 如果关键词出现在否定句（含"不/无/没/非"等）中，不判为失败
    - 例如"不提供猪肉食品"中的"猪肉"不应判失败
    
    搜索范围：output.text + JSON 字符串化（覆盖纯 JSON 输出场景）
    """
    must = fixture.expected.must_contain_keywords or []
    must_not = fixture.expected.must_not_contain_keywords or []
    mode = getattr(fixture.expected, "keyword_match_mode", "all")
    
    # 搜索范围：text + JSON 字符串化
    text = output.text
    json_str = json.dumps(output.json, ensure_ascii=False) if output.json else ""
    combined_text = text + json_str
    
    if mode == "any":
        any_hit = any(kw in combined_text for kw in must)
        missing = [] if any_hit else list(must)
    else:
        missing = [kw for kw in must if kw not in combined_text]

    # 上下文感知：过滤掉否定句中的 must_not 关键词
    _NEGATION_WORDS = {"不", "无", "没", "非", "禁", "勿", "未", "别", "远离", "避免", "避开", "排除", "剔除"}
    
    def _is_negation_context(text: str, keyword: str) -> bool:
        """检查关键词是否出现在否定句中"""
        idx = text.find(keyword)
        if idx == -1:
            return False
        # 取关键词前 15 个字符的上下文
        context = text[max(0, idx - 15):idx]
        return any(neg in context for neg in _NEGATION_WORDS)

    forbidden = [kw for kw in must_not if kw in text and not _is_negation_context(text, kw)]

    if not missing and not forbidden:
        return EvalResult(
            passed=True,
            details={"mustHit": len(must), "mustNotHit": len(must_not), "mode": mode},
        )

    reasons: list[str] = []
    if missing:
        reasons.append(f"缺少必含关键词: {', '.join(missing)}")
    if forbidden:
        reasons.append(f"出现禁用关键词: {', '.join(forbidden)}")
    return EvalResult(passed=False, reason="; ".join(reasons))


# ============================================================
# 4. tool_call_audit
# ============================================================

@register_evaluator("tool_call_audit")
def tool_call_audit(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证工具调用 min_calls/max_calls 合规"""
    rules = fixture.expected.tool_calls
    if not rules:
        return EvalResult(passed=True, reason="no tool_calls rules, skipping")

    calls = output.tool_calls or []
    violations: list[str] = []

    for rule_dict in rules:
        rule_name_raw = rule_dict.get("name", "")
        rule_name = _normalize_tool_name(rule_name_raw)
        count = sum(1 for c in calls if _normalize_tool_name(c.name) == rule_name)

        min_calls = rule_dict.get("min_calls")
        max_calls = rule_dict.get("max_calls")

        if min_calls is not None and count < min_calls:
            violations.append(f"{rule_name_raw} 调用 {count} 次 < 至少 {min_calls} 次")
        if max_calls is not None and max_calls >= 0 and count > max_calls:
            violations.append(f"{rule_name_raw} 调用 {count} 次 > 至多 {max_calls} 次")

    if not violations:
        return EvalResult(passed=True, details={"totalCalls": len(calls)})
    return EvalResult(passed=False, reason="; ".join(violations))


# ============================================================
# 5. pace_consistency
# ============================================================

@register_evaluator("pace_consistency")
def pace_consistency(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证 days 数 + 每天活动数不超 max_activities_per_day"""
    expected_days = fixture.expected.days
    max_per_day = fixture.expected.max_activities_per_day
    json_data = output.json

    violations: list[str] = []

    if expected_days:
        actual_days: int | None = None

        if json_data and isinstance(json_data.get("days"), int):
            actual_days = json_data["days"]
        else:
            day_matches = re.findall(
                r"(?:Day\s*\d+|第\s*\d+\s*天)", output.text, re.IGNORECASE
            )
            if day_matches:
                actual_days = len(
                    set(m.lower().replace(" ", "") for m in day_matches)
                )

        if actual_days is None:
            return EvalResult(
                passed=False,
                reason="output 找不到天数信息（既无 JSON.days 也无 Day N 文本）",
            )
        if actual_days != expected_days:
            violations.append(f"行程天数 {actual_days} ≠ 期望 {expected_days}")

    if max_per_day:
        if json_data and isinstance(json_data.get("dailyItinerary"), list):
            for i, day in enumerate(json_data["dailyItinerary"]):
                filled_slots = 0
                for slot_key in ("morning", "afternoon", "evening"):
                    slot = day.get(slot_key)
                    if slot and slot.get("spot"):
                        filled_slots += 1
                if filled_slots > max_per_day:
                    violations.append(
                        f"Day {i + 1} 有 {filled_slots} 个活动 > 上限 {max_per_day}"
                    )

    if not violations:
        return EvalResult(passed=True, details={"maxPerDay": max_per_day})
    return EvalResult(passed=False, reason="; ".join(violations))
