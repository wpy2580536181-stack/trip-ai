"""
多轮对话 + 反例 evaluator

- destination_override: 跟随最新目的地指令
- context_memory: 是否记得上文关键信息
- no_forced_itinerary: 不该硬塞完整行程（反例场景）
"""

from __future__ import annotations

import re
from typing import Any

from eval.registry import register_evaluator
from eval.types import AgentOutput, EvalResult, Fixture

# 硬塞行程检测模式
_ITINERARY_HARDCODE_PATTERNS = [
    re.compile(r"第\s*\d+\s*天"),
    re.compile(r"Day\s*\d+", re.IGNORECASE),
    re.compile(r"D\d+", re.IGNORECASE),
    re.compile(r"行程安排[:：]"),
]

# 结构化行程标记模式（匹配多个才算硬塞，单个引用不算）
_STRUCT_DAY_PATTERNS = [
    re.compile(r"第\s*\d+\s*天"),
    re.compile(r"Day\s*\d+", re.IGNORECASE),
]


def _get_daily_slots(json_data: dict[str, Any] | None):
    """Yield (day_index, slot_key, slot_dict) for all non-empty slots."""
    if not json_data or not isinstance(json_data.get("dailyItinerary"), list):
        return
    for i, day in enumerate(json_data["dailyItinerary"]):
        for slot_key in ("morning", "afternoon", "evening"):
            slot = day.get(slot_key)
            if slot and slot.get("spot"):
                yield i, slot_key, slot


# ============================================================
# 1. destination_override
# ============================================================

@register_evaluator("destination_override")
def destination_override(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """
    验证多轮对话中用户改了目的地后，Agent 跟随了最新指令。

    用 must_contain_pois 检查目标城市 POI 是否出现，
    用 must_not_contain_keywords 检查原目的地关键词是否消失。
    """
    if not fixture.input.history:
        return EvalResult(passed=True, reason="无 history，非多轮对话，跳过")

    required = fixture.expected.must_contain_pois or []
    target_cities = {p.get("city") for p in required if p.get("city")}

    if not target_cities:
        return EvalResult(passed=True, reason="no target city specified in must_contain_pois, skipping")

    banned_keywords = fixture.expected.must_not_contain_keywords or []
    violations: list[str] = []

    # JSON 行程里检查 POI 是否落在目标城市
    for day_idx, _slot_key, slot in _get_daily_slots(output.json):
        spot = slot["spot"]
        banned_hit = next((kw for kw in banned_keywords if kw in spot), None)
        if banned_hit:
            violations.append(
                f"Day {day_idx + 1} 推荐了原目的地 POI：\"{spot}\"（含\"{banned_hit}\"），未跟随新指令"
            )

    # 文本里也检查原目的地关键词
    for kw in banned_keywords:
        if kw in output.text:
            violations.append(f"文本中提到原目的地关键词：\"{kw}\"")

    if not violations:
        return EvalResult(passed=True, details={"targetCities": list(target_cities)})
    return EvalResult(passed=False, reason="; ".join(violations))


# ============================================================
# 2. context_memory
# ============================================================

@register_evaluator("context_memory")
def context_memory(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """
    验证 Agent 记得上文的关键信息。

    用 must_contain_keywords 包含"上文关键实体"，
    全部命中 → pass（Agent 记得），否则 fail。
    """
    if not fixture.input.history:
        return EvalResult(passed=True, reason="无 history，非多轮对话，跳过")

    must = fixture.expected.must_contain_keywords or []
    if not must:
        return EvalResult(passed=True, reason="no must_contain_keywords, skipping")

    # 查找最后一条 assistant 消息（用于上下文 POI 提取，仅作详情）
    last_assistant = None
    for h in reversed(fixture.input.history):
        if h.get("role") == "assistant":
            last_assistant = h
            break

    if not last_assistant:
        return EvalResult(passed=True, reason="no last assistant message, skipping")

    # 抽取上文 POI 名（粗略：2-10 字的连续中文）
    upper_context_pois = re.findall(
        r"[\u4e00-\u9fa5]{2,10}", last_assistant.get("content", "")
    )

    # 验证 output.text 至少包含 must 中的关键词
    missing = [kw for kw in must if kw not in output.text]
    if not missing:
        return EvalResult(
            passed=True,
            details={
                "mustHit": len(must),
                "upperContextPOIs": upper_context_pois[:3],
            },
        )
    return EvalResult(passed=False, reason=f"缺失上文关键信息：{', '.join(missing)}")


# ============================================================
# 3. no_forced_itinerary
# ============================================================

@register_evaluator("no_forced_itinerary")
def no_forced_itinerary(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """
    验证 Agent 不该硬塞具体行程（反例场景）。

    检测：
    1) output.json 不应有非空 dailyItinerary 数组
    2) output.text 不含 "Day 1"/"第1天" 等结构化行程词
    3) 不含 must_not_contain_keywords 里的硬塞关键词
    """
    # 判断 fixture 是否是"反例"场景
    exp = fixture.expected
    is_rejection_fixture = (
        (exp.days == 0 and exp.is_recommendation is not True)
        or exp.json_valid is False
        or exp.is_recommendation is True
    )

    if not is_rejection_fixture:
        return EvalResult(passed=True, reason="非反例 fixture，跳过")

    violations: list[str] = []

    # 1. JSON 行程不该被硬塞
    json_data = output.json
    if (
        json_data
        and isinstance(json_data.get("dailyItinerary"), list)
        and len(json_data["dailyItinerary"]) > 0
    ):
        violations.append(
            f"反例场景却输出了 {len(json_data['dailyItinerary'])} 天行程"
        )

    # 2. 文本里不该有结构化行程词
    #    对于 Day/第N天 模式：单个引用可能是追问场景的合理引用，需 2+ 个匹配才判为硬塞
    for pat in _ITINERARY_HARDCODE_PATTERNS:
        matches = pat.findall(output.text)
        is_struct_day = any(sp.pattern == pat.pattern for sp in _STRUCT_DAY_PATTERNS)
        if is_struct_day:
            # Day/第N天 模式：需要 4+ 个匹配才判定为结构化行程
            # 追问场景中引用 2-3 次同一天是合理的（如"Day 2 推荐...我并没有在 Day 2 推荐..."）
            # 真正的行程输出会有多天结构（Day 1 + Day 2 + Day 3 = 至少 3 个不同天）
            if len(matches) >= 4:
                violations.append(f"反例场景包含多个硬塞关键词：{pat.pattern}（匹配 {len(matches)} 次）")
        else:
            # 其他模式（D\d+、行程安排：）：单次匹配即违规
            if matches:
                violations.append(f"反例场景包含硬塞关键词：{pat.pattern}")

    # 3. 必不含关键词
    banned = fixture.expected.must_not_contain_keywords or []
    banned_hit = [kw for kw in banned if kw in output.text]
    if banned_hit:
        violations.append(f"出现硬塞关键词：{', '.join(banned_hit)}")

    if not violations:
        return EvalResult(passed=True)
    return EvalResult(passed=False, reason="; ".join(violations))
