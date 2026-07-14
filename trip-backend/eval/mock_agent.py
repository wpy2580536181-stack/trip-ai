"""
Mock Agent

按 fixture tags 分类返回确定性输出，用于本地测试 evaluator 而不依赖真实 LLM。

注意：mock 仅用于"evaluator 实现自测"。
生产 eval 必须用 --real 跑真实 agent。
"""

from __future__ import annotations

from eval.types import AgentOutput, Fixture, ToolCall


# 常见城市列表，用于从消息中提取城市名
_KNOWN_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "重庆", "杭州", "西安",
    "南京", "苏州", "武汉", "长沙", "青岛", "厦门", "大连", "昆明",
    "丽江", "大理", "三亚", "桂林", "张家界", "黄山", "拉萨", "敦煌",
    "东京", "京都", "大阪", "首尔", "曼谷", "巴黎", "伦敦", "纽约",
]


def _extract_city_from_message(message: str) -> str | None:
    """从消息中提取第一个匹配的城市名。"""
    for city in _KNOWN_CITIES:
        if city in message:
            return city
    return None


def mock_agent(fixture: Fixture) -> AgentOutput:
    """Mock agent：根据 fixture.tags 分类返回确定性输出。

    - 反例/拒答 fixture → 返回简短文本
    - 雨天 fixture → 返回室内推荐 + getWeather tool call
    - 行程 fixture → 返回结构化 JSON + markdown
    - 默认 → 返回简短文本
    """
    tags = fixture.tags or []
    message = fixture.input.message

    # 反例 fixture（rejection / off-topic）
    if "rejection" in tags or "off-topic" in tags:
        return AgentOutput(
            text="推荐这几个目的地：青岛、桂林、丽江，都是 6 月适合的。",
            tool_calls=[ToolCall(name="retrieve_knowledge")],
        )

    # 雨天 fixture（weather-adaptation）
    if "weather-adaptation" in tags:
        return AgentOutput(
            text="雨天推荐浙江省博物馆、灵隐寺，备选室内方案。",
            tool_calls=[
                ToolCall(name="getWeather"),
                ToolCall(name="retrieve_knowledge"),
            ],
        )

    # 行程 fixture（有 days 字段）
    if fixture.expected.days and fixture.expected.days > 0:
        city = _extract_city_from_message(message) or "成都"
        pois = [
            p.get("name") or p.get("name_contains")
            for p in (fixture.expected.must_contain_pois or [])
        ]
        pois = [p for p in pois if p]

        days = fixture.expected.days
        daily_itinerary = []
        for i in range(days):
            daily_itinerary.append({
                "day": i + 1,
                "morning": {"spot": pois[i * 3] if i * 3 < len(pois) else f"{city}景点{i * 3 + 1}"},
                "afternoon": {"spot": pois[i * 3 + 1] if i * 3 + 1 < len(pois) else f"{city}景点{i * 3 + 2}"},
                "evening": {
                    "spot": pois[i * 3 + 2] if i * 3 + 2 < len(pois) else f"{city}美食{i * 3 + 3}",
                    "ticket": "￥100",
                },
            })

        json_obj = {
            "city": city,
            "days": days,
            "totalBudget": 3000,
            "dailyItinerary": daily_itinerary,
            "budgetBreakdown": {
                "accommodation": 1000,
                "food": 800,
                "transportation": 500,
                "tickets": 500,
                "other": 200,
            },
            "tips": ["多喝水", "注意防晒"],
        }

        text_pois = "、".join(pois)
        keywords = "、".join(fixture.expected.must_contain_keywords or [])
        text = f"{city} {days} 天行程：{text_pois}。{keywords}"

        return AgentOutput(
            text=text,
            json=json_obj,
            tool_calls=[
                ToolCall(name="retrieve_knowledge"),
                ToolCall(name="retrieve_knowledge"),
            ],
        )

    # 默认
    return AgentOutput(
        text="这是 mock 响应。",
        tool_calls=[],
    )
