"""
领域 evaluator

- pet_constraint_check: 宠物友好场所校验
- dietary_constraint_check: 饮食禁忌校验
- weather_adaptation_check: 天气应对校验
- budget_field_present: 预算字段完整性
- kid_friendly_check: 亲子友好校验
"""

from __future__ import annotations

import re
from typing import Any

from eval.registry import register_evaluator
from eval.types import AgentOutput, EvalResult, Fixture

# ============================================================
# Constants
# ============================================================

# 宠物禁入场所关键词
PET_BANNED_KEYWORDS = [
    "动物园",
    "野生动物园",
    "水族馆",
    "海洋馆",
    "美术馆",
    "科技馆",
    "展览馆",
]

PET_REQUIRED_KEYWORDS = ["宠物", "牵引绳", "防疫", "便便", "狗证", "宠物友好", "遛狗"]

PET_MENTION_RE = re.compile(
    r"宠物|狗|猫|金毛|柯基|泰迪|边牧|拉布拉多|萨摩|哈士奇|比熊|贵宾"
)

# 饮食规则
DIETARY_RULES: dict[str, dict[str, Any]] = {
    "halal": {
        "label": "清真",
        "required": ["清真"],
        "banned": ["猪肉", "培根", "火腿", "香肠", "烤肠", "猪骨", "猪蹄"],
    },
    "vegetarian": {
        "label": "素食",
        "required": ["素食", "素菜", "斋饭"],
        "banned": ["牛肉", "羊肉", "鸡肉", "猪肉", "鱼", "虾", "蟹"],
    },
    "vegan": {
        "label": "纯素",
        "required": ["素食", "纯素", "植物"],
        "banned": ["牛奶", "鸡蛋", "奶酪", "黄油", "蜂蜜", "牛肉", "猪肉"],
    },
    "glutenfree": {
        "label": "无麸质",
        "required": ["无麸质", "面筋"],
        "banned": ["面条", "面包", "馒头", "包子", "饺子皮"],
    },
}

DIETARY_DETECT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("halal", re.compile(r"穆斯林|清真|halal", re.IGNORECASE)),
    ("vegan", re.compile(r"纯素|vegan", re.IGNORECASE)),
    ("vegetarian", re.compile(r"素食|不吃肉|吃素")),
    ("glutenfree", re.compile(r"无麸质|麸质过敏|gluten", re.IGNORECASE)),
]

# 天气
WEATHER_MENTION_RE = re.compile(r"雨|雪|台风|高温|寒冷|雾霾|沙尘|暴晒")
WEATHER_ADAPTATION_RE = re.compile(r"雨|雪|室内|备选|避雨|防寒|防晒|防雾霾")
WEATHER_BAD_KEYWORDS = ["露天", "草坪", "野餐", "露营", "骑行环湖", "冲浪", "日光浴"]
WEATHER_SAFE_CONTEXT_RE = re.compile(r"室内|改|避|不推荐|避免|建议改")

# 亲子
KID_MENTION_RE = re.compile(r"孩子|小孩|宝宝|儿子|女儿|亲子|带.+岁|家庭")
KID_TIP_RE = re.compile(r"儿童|孩子|亲子|家长|安全|休息|午休|体力")
KID_BAD_KEYWORDS = [
    "徒步", "登山", "攀岩", "蹦极", "夜店",
    "通宵", "潜水", "跳伞", "飙车", "鬼屋",
]


# ============================================================
# Helpers
# ============================================================

def _is_in_avoidance_context(text: str, keyword: str, negation_words: list[str] | None = None) -> bool:
    """
    检查某个 banned 关键词是否在"避免/无/不"语境中出现。
    "无猪肉""避免猪肉""全聚德已排除" 都是合规的。
    """
    if negation_words is None:
        negation_words = [
            "无", "不", "没", "避免", "拒绝", "排除", "慎", "禁",
            "已帮你排除", "已排除", "未标注", "未推荐",
        ]
    idx = 0
    while True:
        idx = text.find(keyword, idx)
        if idx == -1:
            return False
        start = max(0, idx - 12)
        end = idx + len(keyword) + 30
        ctx = text[start:end]
        if any(neg in ctx for neg in negation_words):
            return True
        idx += len(keyword)


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
# 1. pet_constraint_check
# ============================================================

@register_evaluator("pet_constraint_check")
def pet_constraint_check(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证行程没有宠物禁入场所 + 提到宠物注意事项"""
    message = fixture.input.message
    if not PET_MENTION_RE.search(message):
        return EvalResult(passed=True, reason="用户没提宠物，跳过")

    text = output.text
    violations: list[str] = []

    # 必含宠物提示
    has_pet_tip = any(kw in text for kw in PET_REQUIRED_KEYWORDS)
    if not has_pet_tip:
        violations.append(
            f"未提示宠物注意事项（缺少关键词：{'/'.join(PET_REQUIRED_KEYWORDS[:3])} 等）"
        )

    # 禁入场所（文本）
    banned_hit = [kw for kw in PET_BANNED_KEYWORDS if kw in text]
    if banned_hit:
        violations.append(f"推荐了宠物禁入场所：{', '.join(banned_hit)}")

    # 禁入场所（JSON 行程）
    for day_idx, _slot_key, slot in _get_daily_slots(output.json):
        spot = slot["spot"]
        hit = next((kw for kw in PET_BANNED_KEYWORDS if kw in spot), None)
        if hit:
            violations.append(f"Day {day_idx + 1} 推荐了宠物禁入 POI：\"{spot}\"（含\"{hit}\"）")

    if not violations:
        return EvalResult(passed=True)
    return EvalResult(passed=False, reason="; ".join(violations))


# ============================================================
# 2. dietary_constraint_check
# ============================================================

@register_evaluator("dietary_constraint_check")
def dietary_constraint_check(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证饮食禁忌合规"""
    message = fixture.input.message
    detected: list[str] = []

    for key, pattern in DIETARY_DETECT_PATTERNS:
        # vegan 优先于 vegetarian，避免重复检测
        if key == "vegetarian" and "vegan" in detected:
            continue
        if pattern.search(message):
            detected.append(key)

    if not detected:
        return EvalResult(passed=True, reason="用户没提饮食禁忌，跳过")

    text = output.text
    violations: list[str] = []

    for key in detected:
        rule = DIETARY_RULES[key]
        has_required = any(kw in text for kw in rule["required"])
        if not has_required:
            violations.append(
                f"未明确提到\"{rule['label']}\"相关（缺少：{'/'.join(rule['required'])}）"
            )

        # 排除"避免"语境（扩展否定词列表，覆盖更多场景）
        negation_words_extended = [
            "无", "不", "没", "避免", "拒绝", "排除", "慎", "禁",
            "已帮你排除", "已排除", "未标注", "未推荐",
            "不含", "不提供", "不涉及", "不会有", "全程无",
        ]
        banned_hit = [
            kw for kw in rule["banned"]
            if kw in text and not _is_in_avoidance_context(text, kw, negation_words_extended)
        ]
        if banned_hit:
            violations.append(f"行程含 {rule['label']} 禁忌食材：{', '.join(banned_hit)}")

    if not violations:
        return EvalResult(passed=True, details={"detectedRules": detected})
    return EvalResult(passed=False, reason="; ".join(violations))


# ============================================================
# 3. weather_adaptation_check
# ============================================================

@register_evaluator("weather_adaptation_check")
def weather_adaptation_check(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证天气应对合规"""
    message = fixture.input.message
    if not WEATHER_MENTION_RE.search(message):
        return EvalResult(passed=True, reason="用户没提天气状况，跳过")

    text = output.text
    violations: list[str] = []

    # 1. 必含应对关键词
    if not WEATHER_ADAPTATION_RE.search(text):
        violations.append("未提供天气应对方案")

    # 2. 必不含露天推荐（排除"室内/改/避"等安全上下文）
    bad_hit = []
    for kw in WEATHER_BAD_KEYWORDS:
        idx = text.find(kw)
        if idx == -1:
            continue
        ctx_start = max(0, idx - 20)
        ctx_end = idx + len(kw) + 20
        ctx = text[ctx_start:ctx_end]
        if not WEATHER_SAFE_CONTEXT_RE.search(ctx):
            bad_hit.append(kw)
    if bad_hit:
        violations.append(f"推荐了露天活动（与天气不符）：{', '.join(bad_hit)}")

    # 3. 应调用 getWeather 工具
    calls = output.tool_calls or []
    weather_call = next(
        (c for c in calls if _normalize_tool_name(c.name) == "getweather"),
        None,
    )
    if not weather_call:
        violations.append("未调用 getWeather 工具查询实际天气")

    if not violations:
        return EvalResult(passed=True, details={"weatherCall": weather_call is not None})
    return EvalResult(passed=False, reason="; ".join(violations))


def _normalize_tool_name(name: str) -> str:
    return re.sub(r"[_\-]", "", name.lower())


# ============================================================
# 4. budget_field_present
# ============================================================

@register_evaluator("budget_field_present")
def budget_field_present(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证每个时段 slot 都有 ticket 字段（含价格信息）"""
    if not fixture.expected.activities_have_price_field:
        return EvalResult(passed=True, reason="fixture 未要求 price 字段，跳过")

    json_data = output.json
    if not json_data or not isinstance(json_data.get("dailyItinerary"), list):
        return EvalResult(passed=False, reason="output.json.dailyItinerary 不存在")

    price_re = re.compile(r"￥|¥|元|\d+\s*元")
    missing: list[str] = []

    for day_idx, slot_key, slot in _get_daily_slots(json_data):
        ticket = slot.get("ticket", "")
        if not ticket or not price_re.search(ticket):
            missing.append(f"Day {day_idx + 1} {slot_key}（{slot['spot']}）")

    if not missing:
        return EvalResult(passed=True)

    shown = missing[:5]
    suffix = f" 等 {len(missing)} 项" if len(missing) > 5 else ""
    return EvalResult(
        passed=False,
        reason=f"以下时段缺价格：{'; '.join(shown)}{suffix}",
    )


# ============================================================
# 5. kid_friendly_check
# ============================================================

@register_evaluator("kid_friendly_check")
def kid_friendly_check(output: AgentOutput, fixture: Fixture) -> EvalResult:
    """验证亲子适配：体力约束 + 必含儿童相关提示"""
    message = fixture.input.message
    if not KID_MENTION_RE.search(message):
        return EvalResult(passed=True, reason="用户没提孩子，跳过")

    text = output.text
    violations: list[str] = []

    # 1. 必含儿童相关提示
    if not KID_TIP_RE.search(text):
        violations.append("未提示儿童注意事项")

    # 2. 必不含儿童不宜（文本）
    bad_hit = [kw for kw in KID_BAD_KEYWORDS if kw in text]
    if bad_hit:
        violations.append(f"推荐了儿童不宜活动：{', '.join(bad_hit)}")

    # 3. JSON 行程里也检查 POI 名
    for day_idx, _slot_key, slot in _get_daily_slots(output.json):
        spot = slot["spot"]
        hit = next((kw for kw in KID_BAD_KEYWORDS if kw in spot), None)
        if hit:
            violations.append(f"Day {day_idx + 1} 推荐了儿童不宜 POI：\"{spot}\"")

    if not violations:
        return EvalResult(passed=True)
    return EvalResult(passed=False, reason="; ".join(violations))
